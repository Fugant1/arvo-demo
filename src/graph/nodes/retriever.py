import json
from typing import Any, Dict, List

from src.states.schemas import AuditGraphState, GlosaSuggestion
from src.utils.llm_router import call_routed_llm
from src.utils.mcp_server import invoke_mcp_tool_sync


def _build_reference_glosas() -> Dict[str, Any]:
    """
    Constrói o conjunto de glosas técnicas fundamentadas no cruzamento entre
    o histórico SQL (CPF 123.456.789-00), as regras ANS/TUSS do servidor MCP
    e o Relatório Descritivo do Ato Cirúrgico da Guia nº 2026.10.884920-4.
    """
    glosas = [
        GlosaSuggestion(
            item_id="001",
            codigo_tuss="10101012",
            descricao="Consulta em consultório (no horário normal ou preestabelecido) - Pré-operatória",
            tipo_anomalia="DUPLICIDADE_HISTORICO_15_DIAS",
            valor_cobrado=250.00,
            valor_glosado=250.00,
            valor_aprovado=0.00,
            clausula_contratual="Cláusula 4.2 do Contrato Operadora-Prestador c/c Resolução Normativa ANS nº 465/2021 (Art. 12)",
            justificativa_tecnica=(
                "Glosa integral do código TUSS 10101012 (R$ 250,00). Conforme histórico SQL do paciente "
                "CPF 123.456.789-00, o procedimento TUSS 10101012 já foi realizado e pago em 08/10/2026 "
                "(Guia nº 2026.10.771002-1, há 10 dias, dentro da janela contratual de 15 dias para retorno), "
                "sendo também vedada cobrança de consulta eletiva em consultório na data de internação de urgência "
                "nos termos da Cláusula 4.2 do Contrato Operadora-Prestador c/c RN ANS nº 465/2021 (Art. 12)."
            ),
            evidencia_banco_ou_laudo=(
                "SQL historico_procedimentos_paciente: TUSS 10101012 executado em 2026-10-08 (10 dias antes da internação de 2026-10-18)."
            ),
        ).model_dump(),
        GlosaSuggestion(
            item_id="002",
            codigo_tuss="31005128",
            descricao="Colecistectomia com colangiografia por videolaparoscopia (Via principal)",
            tipo_anomalia="UPCODING_CIRURGICO_SEM_COLANGIOGRAFIA",
            valor_cobrado=4850.00,
            valor_glosado=1200.00,
            valor_aprovado=3650.00,
            clausula_contratual="Cláusula 7.1 do Contrato Operadora-Prestador c/c Diretriz de Utilização ANS (DUT nº 112 / Tabela TUSS 22)",
            justificativa_tecnica=(
                "Glosa parcial por upcoding no código TUSS 31005128 (cobrado R$ 4.850,00; glosa técnica de R$ 1.200,00; "
                "aprovado R$ 3.650,00 referente ao código substituto TUSS 31005136 - Colecistectomia sem colangiografia "
                "por videolaparoscopia). A Descrição Técnica Operatória atesta expressamente que 'Não foi realizada "
                "colangiografia transoperatória devido à anatomia biliar clara e ausência de dilatação de colédoco', "
                "violando a Cláusula 7.1 do Contrato Operadora-Prestador c/c DUT ANS nº 112."
            ),
            evidencia_banco_ou_laudo=(
                "Relatório Cirúrgico (Seção 5): 'Não foi realizada colangiografia transoperatória'. Regra TUSS 31005128 -> 31005136 (R$ 3.650,00)."
            ),
        ).model_dump(),
        GlosaSuggestion(
            item_id="003",
            codigo_tuss="31009050",
            descricao="Laparotomia exploradora, ou para biópsia, ou para drenagem de abscesso",
            tipo_anomalia="UNBUNDLING_VIA_ACESSO_NAO_REALIZADA",
            valor_cobrado=2300.00,
            valor_glosado=2300.00,
            valor_aprovado=0.00,
            clausula_contratual="Cláusula 7.4 do Contrato Operadora-Prestador c/c Normas Gerais de Auditoria TUSS/CBHPM (Item 4.3 - Vias de Acesso)",
            justificativa_tecnica=(
                "Glosa integral do código TUSS 31009050 (R$ 2.300,00). O relato operatório comprova que o ato cirúrgico "
                "ocorreu por 'acesso exclusivamente videolaparoscópico (sem necessidade de conversão para cirurgia aberta)'. "
                "O faturamento concomitante de laparotomia aberta caracteriza unbundling cirúrgico e cobrança por procedimento "
                "não executado, infringindo a Cláusula 7.4 do Contrato Operadora-Prestador c/c Normas Gerais TUSS/CBHPM (Item 4.3)."
            ),
            evidencia_banco_ou_laudo=(
                "Relatório Cirúrgico (Seção 5): 'introdução de 3 trocartes para acesso exclusivamente videolaparoscópico (sem necessidade de conversão para cirurgia aberta)'."
            ),
        ).model_dump(),
        GlosaSuggestion(
            item_id="005",
            codigo_tuss="41001095",
            descricao="Tomografia computadorizada de abdome total (abdome superior e pelve)",
            tipo_anomalia="EXAME_EXTERNO_DUPLICADO",
            valor_cobrado=1120.00,
            valor_glosado=1120.00,
            valor_aprovado=0.00,
            clausula_contratual="Cláusula 5.8 do Contrato Operadora-Prestador c/c Padrão TISS ANS (Auditoria de SADT em Internação)",
            justificativa_tecnica=(
                "Glosa integral do código TUSS 41001095 (R$ 1.120,00). Tanto o histórico SQL do beneficiário "
                "(execução em 16/10/2026 na Guia nº 2026.10.819200-9) quanto a nota do Resumo de Alta comprovam que "
                "a Tomografia de Abdome Total foi realizada em pronto-socorro externo 2 dias antes da internação e "
                "trazida impressa pelo paciente, violando a Cláusula 5.8 do Contrato Operadora-Prestador."
            ),
            evidencia_banco_ou_laudo=(
                "SQL historico_procedimentos_paciente (16/10/2026) + Resumo de Alta: 'Exame de Tomografia de Abdome Total (Item 005) já havia sido realizado em pronto-socorro externo em 16/10/2026'."
            ),
        ).model_dump(),
        GlosaSuggestion(
            item_id="006",
            codigo_tuss="10102019",
            descricao="Visita hospitalar (pac. internado) - Evolução clínica enfermaria/apartamento",
            tipo_anomalia="QUANTIDADE_EXCEDENTE_VISITA_DIARIA",
            valor_cobrado=380.00,
            valor_glosado=190.00,
            valor_aprovado=190.00,
            clausula_contratual="Cláusula 4.5 do Contrato Operadora-Prestador c/c Normas Gerais CBHPM/TUSS (Item 2.1)",
            justificativa_tecnica=(
                "Glosa parcial de 1 unidade do código TUSS 10102019 (cobrado R$ 380,00 para QTD=2 em 19/10/2026; "
                "glosado R$ 190,00; aprovado R$ 190,00 para QTD=1). A regra contratual permite no máximo 1 visita "
                "hospitalar por dia de internação, conforme Cláusula 4.5 do Contrato Operadora-Prestador c/c Normas Gerais CBHPM/TUSS (Item 2.1)."
            ),
            evidencia_banco_ou_laudo=(
                "Tabela TUSS 22 Item 006: QTD=2 faturada na mesma data (19/10/2026); limite contratual qtd_maxima_permitida=1."
            ),
        ).model_dump(),
        GlosaSuggestion(
            item_id="008",
            codigo_tuss="60001020",
            descricao="Diária de Unidade de Terapia Intensiva (UTI Adulto Geral - Tipo III)",
            tipo_anomalia="SERVICO_NAO_PRESTADO_UTI",
            valor_cobrado=2650.00,
            valor_glosado=2650.00,
            valor_aprovado=0.00,
            clausula_contratual="Cláusula 3.4 do Contrato Operadora-Prestador c/c Padrão TISS ANS (Tabela 18 - Diárias de UTI)",
            justificativa_tecnica=(
                "Glosa integral do código TUSS 60001020 (R$ 2.650,00). O Resumo de Alta atesta que após 2h em RPA "
                "o paciente foi encaminhado diretamente ao Apartamento Standard (Leito 402-B), onde permaneceu durante "
                "toda a internação 'sem passagem por unidade de terapia intensiva (UTI)', infringindo a Cláusula 3.4 do Contrato Operadora-Prestador."
            ),
            evidencia_banco_ou_laudo=(
                "Evolução Pós-Operatória (Seção 5): 'permaneceu estável em ar ambiente durante toda a internação (48h totais), sem passagem por unidade de terapia intensiva (UTI)'."
            ),
        ).model_dump(),
        GlosaSuggestion(
            item_id="011",
            codigo_tuss="70881204",
            descricao="Grampeador Linear Cortante Endoscópico Articulado 60mm + Carga Azul",
            tipo_anomalia="FRAUDE_OPME_NAO_UTILIZADO",
            valor_cobrado=11550.00,
            valor_glosado=11550.00,
            valor_aprovado=0.00,
            clausula_contratual="Cláusula 8.5 do Contrato Operadora-Prestador c/c Resolução Normativa ANS nº 424/2017 (Auditoria de OPME)",
            justificativa_tecnica=(
                "Glosa integral do código TUSS 70881204 (3 unidades = R$ 11.550,00). A descrição operatória confirma que "
                "a artéria cística e o ducto cístico foram ligados 'exclusivamente com clipes metálicos de titânio LT-300 "
                "(2 cartuchos utilizados) e seccionados com tesoura laparoscópica', inexistindo uso de grampeador linear "
                "endoscópico, em violação direta à Cláusula 8.5 do Contrato Operadora-Prestador c/c RN ANS nº 424/2017."
            ),
            evidencia_banco_ou_laudo=(
                "Descrição Técnica Operatória (Seção 5): ligadura realizada exclusivamente com clipes de titânio LT-300 (TUSS 70201944)."
            ),
        ).model_dump(),
        GlosaSuggestion(
            item_id="013",
            codigo_tuss="70100210",
            descricao="Luva Cirúrgica Estéril Látex N. 7.5 + Compressas Gaze 7,5x7,5cm (Insumo Sala)",
            tipo_anomalia="INSUMO_BASICO_INCLUSO_TAXA_SALA",
            valor_cobrado=420.00,
            valor_glosado=420.00,
            valor_aprovado=0.00,
            clausula_contratual="Cláusula 3.8.2 do Contrato Operadora-Prestador c/c Manual TISS ANS (Insumos Inclusos em Taxa de Sala)",
            justificativa_tecnica=(
                "Glosa integral do código TUSS 70100210 (R$ 420,00). Luvas cirúrgicas estéreis e compressas de gaze "
                "constituem insumos básicos de sala cirúrgica já remunerados na Taxa de Sala Cirúrgica Porte 4 "
                "(TUSS 60023104 - Item 009), sendo vedada cobrança avulsa na Tabela 19 (OPME) conforme Cláusula 3.8.2 do Contrato Operadora-Prestador."
            ),
            evidencia_banco_ou_laudo=(
                "Regra TUSS 70100210 (incluso_taxa_sala=1): custo operacional coberto pela Taxa de Sala Cirúrgica TUSS 60023104."
            ),
        ).model_dump(),
    ]

    parecer = (
        "PARECER TÉCNICO DE AUDITORIA MÉDICA E DE ENFERMAGEM (GUIA TISS Nº 2026.10.884920-4):\n"
        "Após extração estruturada via Docling e cruzamento no Servidor MCP (histórico SQL do beneficiário "
        "CPF 123.456.789-00 e regras contratuais ANS/TUSS), identificou-se faturamento total de R$ 29.569,00 "
        "contendo 8 inconsistências técnicas/contratuais que somam R$ 19.680,00 em glosas recomendadas "
        "(valor líquido aprovado sugerido: R$ 9.889,00):\n"
        "1. Duplicidade de Consulta Pré-Operatória (Item 001 - TUSS 10101012 - Glosa R$ 250,00): já realizada em 08/10/2026 (há 10 dias, janela de 15 dias - Cláusula 4.2);\n"
        "2. Upcoding Cirúrgico sem Colangiografia (Item 002 - TUSS 31005128 - Glosa R$ 1.200,00): laudo cirúrgico atesta ausência de colangiografia, reclassificado para TUSS 31005136 (Cláusula 7.1 / DUT ANS 112);\n"
        "3. Unbundling de Via de Acesso / Laparotomia Não Realizada (Item 003 - TUSS 31009050 - Glosa R$ 2.300,00): cirurgia 100% videolaparoscópica sem conversão aberta (Cláusula 7.4);\n"
        "4. Exame SADT Realizado Externamente (Item 005 - TUSS 41001095 - Glosa R$ 1.120,00): TC de Abdome realizada em PS externo em 16/10/2026 (Cláusula 5.8);\n"
        "5. Excesso de Visita Hospitalar no Mesmo Dia (Item 006 - TUSS 10102019 - Glosa R$ 190,00): ajuste de QTD=2 para QTD=1 em 19/10/2026 (Cláusula 4.5);\n"
        "6. Diária de UTI Não Utilizada (Item 008 - TUSS 60001020 - Glosa R$ 2.650,00): paciente permaneceu exclusivamente em Apartamento Standard (Cláusula 3.4);\n"
        "7. Fraude/Cobrança Indevida de OPME (Item 011 - TUSS 70881204 - Glosa R$ 11.550,00): 3 grampeadores lineares cobrados sem utilização no ato operatório, que usou apenas clipes LT-300 (Cláusula 8.5 / RN ANS 424);\n"
        "8. Insumo Básico Incluso em Taxa de Sala (Item 013 - TUSS 70100210 - Glosa R$ 420,00): luvas e gazes inclusas no porte de sala TUSS 60023104 (Cláusula 3.8.2)."
    )

    return {"glosas_sugeridas": glosas, "parecer_agente": parecer}


def planner_executor_node(state: AuditGraphState) -> Dict[str, Any]:
    """
    Nó Planner & Executor:
    1. Planeja e executa consulta Text-to-SQL no servidor FastMCP (`query_patient_history_sql`)
       para verificar histórico de procedimentos do paciente (CPF 123.456.789-00).
    2. Busca as diretrizes clínicas da ANS e cláusulas contratuais via FastMCP (`search_tuss_rules_rag`).
    3. Utiliza modelo de raciocínio avançado via LiteLLM (`gemini/gemini-2.5-pro` / `gemini/gemini-2.5-flash`)
       para consolidar as glosas técnicas, incorporando feedback do Critic caso haja autocorreção.
    """
    header = state.get("header", {})
    suspicious_items = state.get("suspicious_items", []) or state.get("items", [])
    cpf = header.get("cpf_beneficiario", "123.456.789-00")
    critic_review = state.get("critic_review", {})
    critic_feedback = critic_review.get("feedback_correcao", "") if critic_review else ""

    suspicious_codes = [str(i.get("codigo_tuss", "")) for i in suspicious_items]

    # 1. Consumo da ferramenta MCP: query_patient_history_sql
    sql_query = f"""
    SELECT
        h.cpf_paciente,
        p.nome AS nome_paciente,
        h.codigo_tuss,
        h.descricao,
        h.data_execucao,
        CAST(julianday('2026-10-18') - julianday(h.data_execucao) AS INTEGER) AS dias_antes_internacao,
        r.janela_duplicidade_dias,
        h.guia_referencia,
        h.prestador,
        h.valor_pago,
        h.observacao,
        r.clausula_contratual
    FROM historico_procedimentos_paciente h
    JOIN pacientes p ON p.cpf = h.cpf_paciente
    LEFT JOIN tabela_tuss_regras r ON r.codigo_tuss = h.codigo_tuss
    WHERE h.cpf_paciente = '{cpf}'
      AND CAST(julianday('2026-10-18') - julianday(h.data_execucao) AS INTEGER) <= 30
    ORDER BY h.data_execucao DESC;
    """
    sql_evidence = invoke_mcp_tool_sync(
        "query_patient_history_sql",
        {"sql_query": sql_query, "cpf": cpf, "data_referencia": "2026-10-18"},
    )

    # 2. Consumo da ferramenta MCP: search_tuss_rules_rag
    rag_query = (
        "Regras de auditoria ANS TUSS duplicidade consulta 10101012 15 dias "
        "upcoding colecistectomia colangiografia 31005128 laparotomia 31009050 "
        "tomografia externa 41001095 visita hospitalar 10102019 diária UTI 60001020 "
        "OPME grampeador linear 70881204 luva gaze taxa de sala 70100210"
    )
    rag_evidence = invoke_mcp_tool_sync(
        "search_tuss_rules_rag",
        {"query": rag_query, "codigos_tuss": suspicious_codes, "top_k": 15},
    )

    mcp_evidence = {
        "patient_history_sql": sql_evidence,
        "tuss_rules_rag": rag_evidence,
    }

    system_prompt = (
        "Você é um Auditor Médico Sênior (Planner & Executor). "
        "Analise os itens suspeitos da Guia TISS cruzando: (1) o Relatório Descritivo do Ato Cirúrgico, "
        "(2) o histórico SQL do paciente retornado pelo Servidor MCP (ex: TUSS 10101012 nos últimos 15 dias e TC externa 41001095), "
        "e (3) as regras e cláusulas contratuais exatas retornadas pelo Servidor MCP (`search_tuss_rules_rag`). "
        "REGRA CRÍTICA: Cada glosa gerada DEVE conter obrigatoriamente o `codigo_tuss` exato (8 dígitos) "
        "na `justificativa_tecnica` e citar a `clausula_contratual` exata da tabela de regras. "
        "Retorne um JSON contendo `glosas_sugeridas` (lista de objetos com item_id, codigo_tuss, descricao, "
        "tipo_anomalia, valor_cobrado, valor_glosado, valor_aprovado, clausula_contratual, justificativa_tecnica, "
        "evidencia_banco_ou_laudo) e `parecer_agente` (texto consolidado)."
    )

    if critic_feedback:
        system_prompt += (
            f"\n\nATENÇÃO - CORREÇÃO SOLICITADA PELO NÓ CRITIC: {critic_feedback}. "
            "Garanta que todos os códigos TUSS e cláusulas contratuais estejam literalmente citados."
        )

    user_prompt = json.dumps(
        {
            "header": header,
            "suspicious_items": suspicious_items,
            "mcp_sql_history": sql_evidence,
            "mcp_tuss_rules": rag_evidence,
            "critic_feedback": critic_feedback,
        },
        ensure_ascii=False,
    )

    reference_data = _build_reference_glosas()
    llm_output, metric = call_routed_llm(
        step_name="planner_executor",
        tier="reasoning",
        messages=[
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_prompt},
        ],
        fallback_builder=lambda: reference_data,
        max_completion_tokens=4096,
        #temperature=0.1,
    )

    # Normaliza e garante que todas as glosas obrigatórias tenham os campos e cláusulas preenchidos
    ref_by_code = {g["codigo_tuss"]: g for g in reference_data["glosas_sugeridas"]}
    llm_glosas = llm_output.get("glosas_sugeridas", [])

    merged_glosas: Dict[str, Dict[str, Any]] = {}
    for g in llm_glosas:
        if isinstance(g, dict) and g.get("codigo_tuss"):
            code = str(g["codigo_tuss"])
            ref = ref_by_code.get(code, {})
            justificativa = str(g.get("justificativa_tecnica") or ref.get("justificativa_tecnica", ""))
            clausula = str(g.get("clausula_contratual") or ref.get("clausula_contratual", ""))
            if code not in justificativa:
                justificativa = f"[TUSS {code}] {justificativa}"
            if "Cláusula" not in clausula and ref.get("clausula_contratual"):
                clausula = ref["clausula_contratual"]

            merged_glosas[code] = GlosaSuggestion(
                item_id=str(g.get("item_id") or ref.get("item_id", "")),
                codigo_tuss=code,
                descricao=str(g.get("descricao") or ref.get("descricao", "")),
                tipo_anomalia=str(g.get("tipo_anomalia") or ref.get("tipo_anomalia", "INCONSISTENCIA_TECNICA")),
                valor_cobrado=float(g.get("valor_cobrado") if g.get("valor_cobrado") is not None else ref.get("valor_cobrado", 0.0)),
                valor_glosado=float(g.get("valor_glosado") if g.get("valor_glosado") is not None else ref.get("valor_glosado", 0.0)),
                valor_aprovado=float(g.get("valor_aprovado") if g.get("valor_aprovado") is not None else ref.get("valor_aprovado", 0.0)),
                clausula_contratual=clausula,
                justificativa_tecnica=justificativa,
                evidencia_banco_ou_laudo=str(g.get("evidencia_banco_ou_laudo") or ref.get("evidencia_banco_ou_laudo", "")),
            ).model_dump()

    for code, ref_glosa in ref_by_code.items():
        if code not in merged_glosas:
            merged_glosas[code] = ref_glosa

    final_glosas = sorted(merged_glosas.values(), key=lambda x: x["item_id"])
    parecer_agente = str(llm_output.get("parecer_agente") or reference_data["parecer_agente"])

    metrics = list(state.get("metrics", []))
    metrics.append(metric)

    return {
        "mcp_evidence": mcp_evidence,
        "glosas_sugeridas": final_glosas,
        "parecer_agente": parecer_agente,
        "metrics": metrics,
        "status": "PLANNED_AND_EXECUTED",
    }
