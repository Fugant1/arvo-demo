import uuid
from typing import Any, Dict, Literal, Optional

from langgraph.checkpoint.memory import MemorySaver
from langgraph.graph import END, START, StateGraph
from langgraph.types import Command

from src.graph.nodes.critic import critic_node
from src.graph.nodes.extractor import extractor_node
from src.graph.nodes.hitl import hitl_node
from src.graph.nodes.retriever import planner_executor_node
from src.graph.nodes.router import triage_router_node
from src.states.schemas import AuditGraphState
from src.utils.db_manager import init_sqlite_db
from src.utils.nosql_store import NoSQLAuditStore


def _route_after_critic(
    state: AuditGraphState,
) -> Literal["planner_executor", "hitl"]:
    """
    Loop de autocorreção: se o nó Critic reprovar alguma justificativa
    (por falta de código TUSS exato ou cláusula contratual) e o limite de
    iterações não tiver sido atingido, retorna ao Planner/Executor.
    """
    review = state.get("critic_review", {})
    iterations = int(state.get("critic_iterations", 0))
    if not review.get("approved", True) and iterations < 2:
        return "planner_executor"
    return "hitl"


def build_audit_graph(checkpointer: Optional[MemorySaver] = None):
    """Constrói e compila o grafo multiagente de auditoria médica no LangGraph."""
    workflow = StateGraph(AuditGraphState)

    workflow.add_node("extractor", extractor_node)
    workflow.add_node("triage_router", triage_router_node)
    workflow.add_node("planner_executor", planner_executor_node)
    workflow.add_node("critic", critic_node)
    workflow.add_node("hitl", hitl_node)

    workflow.add_edge(START, "extractor")
    workflow.add_edge("extractor", "triage_router")
    workflow.add_edge("triage_router", "planner_executor")
    workflow.add_edge("planner_executor", "critic")
    workflow.add_conditional_edges(
        "critic",
        _route_after_critic,
        {
            "planner_executor": "planner_executor",
            "hitl": "hitl",
        },
    )
    workflow.add_edge("hitl", END)

    memory = checkpointer or MemorySaver()
    return workflow.compile(checkpointer=memory)


GLOBAL_CHECKPOINTER = MemorySaver()
AUDIT_GRAPH = build_audit_graph(checkpointer=GLOBAL_CHECKPOINTER)


def run_audit_until_hitl(
    pdf_path: str, thread_id: Optional[str] = None
) -> Dict[str, Any]:
    """
    Executa o fluxo completo (Docling -> Triage Router -> Planner/Executor -> Critic)
    até pausar no `interrupt` do nó HITL.
    """
    init_sqlite_db()
    active_thread_id = thread_id or f"audit-{uuid.uuid4().hex[:10]}"
    config = {"configurable": {"thread_id": active_thread_id}}

    initial_state: AuditGraphState = {
        "thread_id": active_thread_id,
        "pdf_path": pdf_path,
        "critic_iterations": 0,
        "metrics": [],
        "status": "STARTED",
    }

    AUDIT_GRAPH.invoke(initial_state, config=config)
    snapshot = AUDIT_GRAPH.get_state(config)
    state_values = dict(snapshot.values)
    state_values["status"] = "WAITING_HITL"
    return state_values


def resume_audit_from_hitl(
    thread_id: str, decision_payload: Dict[str, Any]
) -> Dict[str, Any]:
    """
    Retoma a execução do LangGraph a partir do `interrupt` identificado por `thread_id`,
    finalizando o parecer de auditoria e persistindo o par de preferência DPO no banco NoSQL.
    """
    config = {"configurable": {"thread_id": thread_id}}
    snapshot = AUDIT_GRAPH.get_state(config)

    if snapshot and snapshot.values:
        final_state = AUDIT_GRAPH.invoke(
            Command(resume=decision_payload), config=config
        )
        return dict(final_state)

    # Fallback resiliente caso o processo tenha sido reiniciado e o estado resida no TinyDB
    store = NoSQLAuditStore()
    saved_session = store.get_session_state(thread_id)
    if not saved_session:
        raise KeyError(f"Sessão thread_id='{thread_id}' não encontrada.")

    state_data = saved_session["state"]
    temp_graph = StateGraph(AuditGraphState)
    temp_graph.add_node("hitl", hitl_node)
    temp_graph.add_edge(START, "hitl")
    temp_graph.add_edge("hitl", END)
    compiled_temp = temp_graph.compile(checkpointer=MemorySaver())

    compiled_temp.invoke(state_data, config=config)
    final_state = compiled_temp.invoke(Command(resume=decision_payload), config=config)
    return dict(final_state)
