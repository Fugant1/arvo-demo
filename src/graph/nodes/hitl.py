from typing import Any, Dict, List
from langgraph.types import interrupt

from src.models.schemas import AuditGraphState
from src.utils.nosql_store import NoSQLAuditStore


def hitl_node(state: AuditGraphState) -> Dict[str, Any]:
    """
    Nó Human-in-the-Loop (HITL):
    1. Persiste o estado preliminar no banco NoSQL (TinyDB em estrutura DynamoDB PK/SK)
       e interrompe a execução do LangGraph via `interrupt(...)` aguardando revisão humana.
    2. Ao ser retomado via `Command(resume=...)` pelo endpoint `POST /hitl/{thread_id}`,
       consolida o parecer final de auditoria e grava o par de preferência
       `(prompt_context, chosen, rejected)` na coleção `dpo_preference_dataset`.
    """
    store = NoSQLAuditStore()
    thread_id = state.get("thread_id", "default-thread")
    glosas_sugeridas = state.get("glosas_sugeridas", [])
    parecer_agente = state.get("parecer_agente", "")
    header = state.get("header", {})

    store.save_session_state(
        thread_id=thread_id,
        status="WAITING_HITL",
        state_data=dict(state),
    )
    store.append_decision_log(
        thread_id=thread_id,
        event_type="GRAPH_INTERRUPTED_FOR_HITL",
        payload={
            "num_glosas_sugeridas": len(glosas_sugeridas),
            "total_glosado_sugerido": round(
                sum(float(g.get("valor_glosado", 0.0)) for g in glosas_sugeridas), 2
            ),
        },
    )

    # Pausa nativa do LangGraph aguardando decisão do auditor humano
    human_input: Dict[str, Any] = interrupt(
        {
            "thread_id": thread_id,
            "message": "Aguardando revisão do auditor humano (APPROVE / EDIT / REJECT).",
            "glosas_sugeridas": glosas_sugeridas,
            "parecer_agente": parecer_agente,
        }
    )

    action = str(human_input.get("action", "APPROVE")).upper()
    auditor_id = str(human_input.get("auditor_id", "auditor.chefe@saudeplena.com.br"))
    auditor_notes = str(human_input.get("auditor_notes") or "").strip()

    chosen_glosas_raw = human_input.get("chosen_glosas")
    if action == "EDIT" and isinstance(chosen_glosas_raw, list) and len(chosen_glosas_raw) > 0:
        glosas_finais: List[Dict[str, Any]] = [
            g.model_dump() if hasattr(g, "model_dump") else dict(g)
            for g in chosen_glosas_raw
        ]
    elif action == "REJECT":
        glosas_finais = (
            [
                g.model_dump() if hasattr(g, "model_dump") else dict(g)
                for g in chosen_glosas_raw
            ]
            if isinstance(chosen_glosas_raw, list)
            else []
        )
    else:
        glosas_finais = list(glosas_sugeridas)

    total_faturado = float(header.get("valor_total_faturado", 29569.00))
    total_glosado_final = round(
        sum(float(g.get("valor_glosado", 0.0)) for g in glosas_finais), 2
    )
    total_aprovado_final = round(max(0.0, total_faturado - total_glosado_final), 2)

    if human_input.get("chosen_summary"):
        parecer_final = str(human_input["chosen_summary"])
    else:
        parecer_final = (
            f"{parecer_agente}\n\n"
            f"--- DELIBERAÇÃO FINAL DA AUDITORIA HUMANA (HITL: {action}) ---\n"
            f"Auditor Responsável: {auditor_id}\n"
            f"Valor Total Faturado: R$ {total_faturado:,.2f} | "
            f"Valor Total Glosado Final: R$ {total_glosado_final:,.2f} | "
            f"Valor Líquido Liberado para Pagamento: R$ {total_aprovado_final:,.2f}."
        )
        if auditor_notes:
            parecer_final += f"\nObservações do Auditor: {auditor_notes}"

    prompt_context = {
        "header": header,
        "suspicious_items": state.get("suspicious_items", []),
        "mcp_evidence": state.get("mcp_evidence", {}),
    }

    agent_suggestion = {
        "glosas": glosas_sugeridas,
        "parecer": parecer_agente,
        "resumo_financeiro": {
            "valor_total_faturado": total_faturado,
            "valor_total_glosado": round(
                sum(float(g.get("valor_glosado", 0.0)) for g in glosas_sugeridas), 2
            ),
        },
    }

    human_final_decision = {
        "glosas": glosas_finais,
        "parecer": parecer_final,
        "auditor_notes": auditor_notes,
        "resumo_financeiro": {
            "valor_total_faturado": total_faturado,
            "valor_total_glosado": total_glosado_final,
            "valor_total_aprovado": total_aprovado_final,
        },
    }

    dpo_record = store.save_dpo_preference_pair(
        thread_id=thread_id,
        auditor_id=auditor_id,
        action=action,
        prompt_context=prompt_context,
        agent_suggestion=agent_suggestion,
        human_final_decision=human_final_decision,
    )

    updated_state = dict(state)
    updated_state.update(
        {
            "human_decision": human_input,
            "glosas_finais": glosas_finais,
            "parecer_final": parecer_final,
            "dpo_record": dpo_record,
            "status": "COMPLETED",
        }
    )

    store.save_session_state(
        thread_id=thread_id,
        status="COMPLETED",
        state_data=updated_state,
    )
    store.append_decision_log(
        thread_id=thread_id,
        event_type="HITL_DECISION_FINALIZED",
        payload={
            "action": action,
            "auditor_id": auditor_id,
            "dpo_record_id": dpo_record["record_id"],
            "valor_total_glosado_final": total_glosado_final,
            "valor_total_aprovado_final": total_aprovado_final,
        },
    )

    return {
        "human_decision": human_input,
        "glosas_finais": glosas_finais,
        "parecer_final": parecer_final,
        "dpo_record": dpo_record,
        "status": "COMPLETED",
    }
