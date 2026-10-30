import json
from typing import Any, Dict, List

from src.states.schemas import AuditGraphState, CriticReview
from src.utils.llm_router import call_routed_llm


def _deterministic_critic_verification(
    glosas: List[Dict[str, Any]], rules_rag: Dict[str, Any]
) -> Dict[str, Any]:
    """
    Verifica deterministicamente se cada glosa sugerida:
    1. Cita explicitamente o código TUSS de 8 dígitos na justificativa técnica;
    2. Cita a Cláusula Contratual correspondente do banco de regras ANS/TUSS;
    3. Possui consistência aritmética (valor_cobrado - valor_glosado == valor_aprovado).
    """
    valid_rules_by_code = {
        str(r.get("codigo_tuss", "")): r for r in rules_rag.get("rules", [])
    }

    reprovados: List[str] = []
    issues: List[str] = []

    if not glosas:
        return CriticReview(
            approved=False,
            score_conformidade=0.0,
            itens_reprovados=["ALL"],
            feedback_correcao="Nenhuma glosa foi gerada para os itens suspeitos. Reexecute o cruzamento SQL e de regras ANS.",
        ).model_dump()

    for g in glosas:
        item_id = str(g.get("item_id", ""))
        code = str(g.get("codigo_tuss", ""))
        justificativa = str(g.get("justificativa_tecnica", ""))
        clausula = str(g.get("clausula_contratual", ""))
        cobrado = float(g.get("valor_cobrado", 0.0))
        glosado = float(g.get("valor_glosado", 0.0))
        aprovado = float(g.get("valor_aprovado", 0.0))

        if code not in justificativa:
            reprovados.append(item_id)
            issues.append(f"Item {item_id}: justificativa não contém o código TUSS exato {code}.")

        if "Cláusula" not in clausula and "Clausula" not in clausula:
            reprovados.append(item_id)
            expected_clause = valid_rules_by_code.get(code, {}).get("clausula_contratual", "Cláusula Contratual ANS")
            issues.append(
                f"Item {item_id} (TUSS {code}): cláusula contratual ausente ou inválida. Cite '{expected_clause}'."
            )

        if abs((cobrado - glosado) - aprovado) > 0.05:
            reprovados.append(item_id)
            issues.append(
                f"Item {item_id} (TUSS {code}): divergência contábil ({cobrado} - {glosado} != {aprovado})."
            )

    unique_reprovados = sorted(set(reprovados))
    approved = len(unique_reprovados) == 0
    score = round(
        max(0.0, (len(glosas) - len(unique_reprovados)) / max(1, len(glosas))), 2
    )
    feedback = (
        "Todas as glosas contêm código TUSS exato, cláusula contratual verificada no MCP e consistência aritmética."
        if approved
        else " | ".join(issues)
    )

    return CriticReview(
        approved=approved,
        score_conformidade=score,
        itens_reprovados=unique_reprovados,
        feedback_correcao=feedback,
    ).model_dump()


def critic_node(state: AuditGraphState) -> Dict[str, Any]:
    """
    Nó Critic (Prevenção de Alucinação e Validação Normativa):
    Utiliza LiteLLM (gemini/gemini-2.5-pro / gemini/gemini-2.5-flash) aliado à checagem
    formal para validar se cada justificativa de glosa cita o código TUSS exato e a
    cláusula contratual correta antes de submeter ao auditor humano (HITL).
    """
    glosas = state.get("glosas_sugeridas", [])
    mcp_evidence = state.get("mcp_evidence", {})
    rules_rag = mcp_evidence.get("tuss_rules_rag", {})
    iterations = int(state.get("critic_iterations", 0)) + 1

    deterministic_check = _deterministic_critic_verification(glosas, rules_rag)

    system_prompt = (
        "Você é o Agente Critic de Auditoria Médica. "
        "Verifique se cada item em `glosas_sugeridas` cita o código TUSS exato de 8 dígitos "
        "na `justificativa_tecnica`, se a `clausula_contratual` confere com as regras oficiais "
        "do Servidor MCP sem alucinação e se os valores glosados estão corretos. "
        "Retorne JSON com: approved (bool), score_conformidade (float 0..1), "
        "itens_reprovados (lista de item_id) e feedback_correcao (string)."
    )

    user_prompt = json.dumps(
        {
            "glosas_sugeridas": glosas,
            "regras_oficiais_mcp": rules_rag,
            "verificacao_deterministica_previa": deterministic_check,
        },
        ensure_ascii=False,
    )

    llm_output, metric = call_routed_llm(
        step_name="critic_validator",
        tier="reasoning",
        messages=[
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_prompt},
        ],
        fallback_builder=lambda: deterministic_check,
        max_completion_tokens=1024,
        #temperature=0.0,
    )

    # A validação formal determinística tem poder de veto caso falte código TUSS ou cláusula
    if not deterministic_check["approved"]:
        final_review = deterministic_check
    else:
        final_review = CriticReview(
            approved=bool(llm_output.get("approved", True)),
            score_conformidade=float(llm_output.get("score_conformidade", 1.0)),
            itens_reprovados=list(llm_output.get("itens_reprovados", [])),
            feedback_correcao=str(
                llm_output.get("feedback_correcao")
                or deterministic_check["feedback_correcao"]
            ),
        ).model_dump()

    metrics = list(state.get("metrics", []))
    metrics.append(metric)

    return {
        "critic_review": final_review,
        "critic_iterations": iterations,
        "metrics": metrics,
        "status": "VALIDATED_BY_CRITIC" if final_review["approved"] else "CRITIC_REJECTED",
    }
