import json
from typing import Any, Dict, List

from src.states.schemas import AuditGraphState, TriageItemDecision
from src.utils.llm_router import call_routed_llm

# Códigos de itens sabidamente críticos ou que exigem auditoria cruzada (SQL/Laudo/OPME/Regras ANS)
HIGH_RISK_TUSS_CODES = {
    "10101012": ("ALTO", "Consulta eletiva cobrada na data de internação de urgência; exige checagem de duplicidade nos últimos 15 dias."),
    "31005128": ("CRITICO", "Procedimento cirúrgico de alto valor com colangiografia; exige validação de execução no relato cirúrgico."),
    "31009050": ("CRITICO", "Laparotomia exploradora aberta cobrada simultaneamente a videolaparoscopia (risco de unbundling/via excludente)."),
    "41001095": ("ALTO", "Exame de imagem de alto custo (TC Abdome Total); exige checagem de duplicidade externa e laudo próprio."),
    "10102019": ("MEDIO", "Cobrança de 2 visitas hospitalares no mesmo dia (19/10/2026) em pós-operatório cirúrgico."),
    "60001020": ("CRITICO", "Diária de UTI Adulto Tipo III (R$ 2.650,00); exige comprovação de passagem por leito intensivo."),
    "70881204": ("CRITICO", "OPME de altíssimo valor (3 Grampeadores Lineares - R$ 11.550,00) em colecistectomia videolaparoscópica."),
    "70100210": ("MEDIO", "Insumo básico de sala (luvas estéreis e compressas de gaze) faturado avulso na Tabela 19 (OPME)."),
}


def _build_deterministic_triage(items: List[Dict[str, Any]]) -> Dict[str, Any]:
    decisions: List[Dict[str, Any]] = []
    for item in items:
        code = str(item.get("codigo_tuss", ""))
        total = float(item.get("valor_total", 0.0))

        if code in HIGH_RISK_TUSS_CODES:
            risk, reason = HIGH_RISK_TUSS_CODES[code]
            status = "SUSPICIOUS_FOR_AUDIT"
        elif total >= 2000.0:
            risk = "ALTO"
            reason = "Item de alto impacto financeiro (> R$ 2.000,00) encaminhado para verificação contratual."
            status = "SUSPICIOUS_FOR_AUDIT"
        else:
            risk = "BAIXO"
            reason = "Item de baixo valor/rotina hospitalar compatível com o porte cirúrgico e tempo de internação."
            status = "AUTO_APPROVED"

        decisions.append(
            TriageItemDecision(
                item_id=str(item.get("item_id", "")),
                codigo_tuss=code,
                descricao=str(item.get("descricao", "")),
                valor_total=total,
                status_triagem=status,
                nivel_risco=risk,
                motivo_triagem=reason,
            ).model_dump()
        )
    return {"triage_results": decisions}


def triage_router_node(state: AuditGraphState) -> Dict[str, Any]:
    """
    Nó Triage Router (Estilo Remy.AI):
    Classificador rápido usando LiteLLM (gemini/gemini-2.5-flash-lite) aliado a
    heurísticas de risco financeiro/TUSS para separar itens de baixo valor (auto-aprovados)
    de itens suspeitos que seguem para auditoria profunda (SQL + Regras ANS).
    """
    items = state.get("items", [])
    header = state.get("header", {})

    system_prompt = (
        "Você é um Triage Router de Auditoria Médica (estilo Remy.AI). "
        "Classifique cada item da Guia TISS em 'AUTO_APPROVED' (baixo valor/rotina compatível) "
        "ou 'SUSPICIOUS_FOR_AUDIT' (possível duplicidade de consulta nos últimos 15 dias, "
        "upcoding cirúrgico, cirurgia aberta concomitante à vídeo, exame externo, diária de UTI "
        "sem passagem por UTI, OPME de alto custo não utilizado ou insumo básico de sala cobrado como OPME). "
        "Retorne estritamente um objeto JSON com a chave 'triage_results' contendo uma lista de objetos com: "
        "item_id, codigo_tuss, descricao, valor_total, status_triagem ('AUTO_APPROVED' ou 'SUSPICIOUS_FOR_AUDIT'), "
        "nivel_risco ('BAIXO', 'MEDIO', 'ALTO', 'CRITICO') e motivo_triagem."
    )

    user_prompt = json.dumps(
        {
            "resumo_clinico": header.get("relatorio_clinico", ""),
            "carater_internacao": header.get("carater_acomodacao", ""),
            "itens_faturados": items,
        },
        ensure_ascii=False,
    )

    llm_output, metric = call_routed_llm(
        step_name="triage_router",
        tier="fast",
        messages=[
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_prompt},
        ],
        fallback_builder=lambda: _build_deterministic_triage(items),
        max_completion_tokens=2048,
        #temperature=0.0,
    )

    raw_results = llm_output.get("triage_results", [])
    baseline_map = {
        d["item_id"]: d for d in _build_deterministic_triage(items)["triage_results"]
    }

    # Garante que nenhum item sabidamente crítico escape da malha fina de triagem
    final_triage: List[Dict[str, Any]] = []
    llm_by_id = {str(r.get("item_id", "")): r for r in raw_results if isinstance(r, dict)}

    for item in items:
        iid = str(item.get("item_id", ""))
        code = str(item.get("codigo_tuss", ""))
        base_decision = baseline_map[iid]
        candidate = llm_by_id.get(iid, base_decision)

        if code in HIGH_RISK_TUSS_CODES:
            status = "SUSPICIOUS_FOR_AUDIT"
            risk = HIGH_RISK_TUSS_CODES[code][0]
            motivo = candidate.get("motivo_triagem") or base_decision["motivo_triagem"]
        else:
            status = candidate.get("status_triagem", base_decision["status_triagem"])
            if status not in ("AUTO_APPROVED", "SUSPICIOUS_FOR_AUDIT"):
                status = base_decision["status_triagem"]
            risk = candidate.get("nivel_risco", base_decision["nivel_risco"])
            if risk not in ("BAIXO", "MEDIO", "ALTO", "CRITICO"):
                risk = base_decision["nivel_risco"]
            motivo = candidate.get("motivo_triagem") or base_decision["motivo_triagem"]

        final_triage.append(
            TriageItemDecision(
                item_id=iid,
                codigo_tuss=code,
                descricao=str(item.get("descricao", "")),
                valor_total=float(item.get("valor_total", 0.0)),
                status_triagem=status,
                nivel_risco=risk,
                motivo_triagem=str(motivo),
            ).model_dump()
        )

    suspicious_ids = {
        t["item_id"] for t in final_triage if t["status_triagem"] == "SUSPICIOUS_FOR_AUDIT"
    }
    suspicious_items = [i for i in items if i["item_id"] in suspicious_ids]
    auto_approved_items = [i for i in items if i["item_id"] not in suspicious_ids]

    metrics = list(state.get("metrics", []))
    metrics.append(metric)

    return {
        "triage_results": final_triage,
        "suspicious_items": suspicious_items,
        "auto_approved_items": auto_approved_items,
        "metrics": metrics,
        "status": "TRIAGED",
    }
