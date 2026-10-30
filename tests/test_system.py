import json
from pathlib import Path
from fastapi.testclient import TestClient

from src.app import app
from src.graph.nodes.critic import _deterministic_critic_verification, critic_node
from src.graph.nodes.extractor import extract_pdf_with_docling
from src.graph.nodes.retriever import planner_executor_node
from src.graph.nodes.router import triage_router_node
from src.states.schemas import BilledItem, GlosaSuggestion
from src.ui import get_single_page_ui_html
from src.utils.db_manager import (
    execute_readonly_sql,
    init_sqlite_db,
    search_tuss_guidelines,
)
from src.utils.llm_router import (
    MODEL_AUDIT_REASONING,
    MODEL_TRIAGE_FAST,
    call_routed_llm,
)
from src.utils.mcp_server import invoke_mcp_tool_sync
from src.utils.nosql_store import NoSQLAuditStore

BASE_DIR = Path(__file__).resolve().parents[1]
PDF_PATH = BASE_DIR / "guia_tiss_auditoria_arvo_teste.pdf"


def test_sqlite_db_and_patient_history():
    """Valida a carga de DB_BASE.sql e o histórico do paciente CPF 123.456.789-00 nos últimos 15 dias."""
    db_path = init_sqlite_db(force_reset=True)
    assert db_path.exists()

    history = execute_readonly_sql(
        """
        SELECT codigo_tuss, CAST(julianday('2026-10-18') - julianday(data_execucao) AS INTEGER) AS dias
        FROM historico_procedimentos_paciente
        WHERE cpf_paciente = '123.456.789-00' AND codigo_tuss = '10101012';
        """
    )
    assert len(history) == 1
    assert history[0]["codigo_tuss"] == "10101012"
    assert history[0]["dias"] <= 15

    rules = execute_readonly_sql("SELECT COUNT(*) AS total FROM tabela_tuss_regras;")
    assert rules[0]["total"] == 15


def test_mcp_server_tools():
    """Valida as ferramentas expostas pelo servidor FastMCP (SQL e RAG de regras TUSS/ANS)."""
    sql_res = invoke_mcp_tool_sync(
        "query_patient_history_sql",
        {"cpf": "123.456.789-00", "data_referencia": "2026-10-18"},
    )
    assert sql_res["row_count"] >= 2
    codes = {r["codigo_tuss"] for r in sql_res["results"]}
    assert "10101012" in codes
    assert "41001095" in codes

    rag_res = invoke_mcp_tool_sync(
        "search_tuss_rules_rag",
        {
            "query": "colangiografia videolaparoscopia grampeador OPME",
            "codigos_tuss": ["31005128", "70881204"],
        },
    )
    assert rag_res["count"] >= 2
    top_codes = {r["codigo_tuss"] for r in rag_res["rules"][:4]}
    assert "31005128" in top_codes
    assert "70881204" in top_codes


def test_litellm_router_metrics():
    """Valida o roteador LiteLLM para os modelos gemini-2.5-flash-lite e gemini-2.5-pro."""
    out_fast, metric_fast = call_routed_llm(
        step_name="unit_test_fast",
        tier="fast",
        messages=[{"role": "user", "content": "Classifique item 10101012"}],
        fallback_builder=lambda: {"status": "SUSPICIOUS_FOR_AUDIT"},
    )
    assert out_fast["status"] == "SUSPICIOUS_FOR_AUDIT"
    assert metric_fast["model"] == MODEL_TRIAGE_FAST
    assert metric_fast["total_tokens"] > 0
    assert metric_fast["latency_ms"] >= 0

    out_pro, metric_pro = call_routed_llm(
        step_name="unit_test_reasoning",
        tier="reasoning",
        messages=[{"role": "user", "content": "Audite código 70881204"}],
        fallback_builder=lambda: {"approved": True},
    )
    assert "approved" in out_pro
    assert metric_pro["model"] in (MODEL_AUDIT_REASONING, "gemini/gemini-2.5-flash")
    assert metric_pro["total_tokens"] > 0


def test_docling_extraction_and_nodes():
    """Valida a extração obrigatória com Docling sobre @guia_tiss_auditoria_arvo_teste.pdf e os nós do grafo."""
    extracted = extract_pdf_with_docling(str(PDF_PATH))
    assert "CARLOS EDUARDO MENDES DA SILVA" in extracted["extracted_markdown"]
    assert extracted["header"]["cpf_beneficiario"] == "123.456.789-00"
    assert len(extracted["items"]) == 15
    assert abs(extracted["header"]["valor_total_faturado"] - 29569.00) < 0.01

    state = {
        "header": extracted["header"],
        "items": extracted["items"],
        "metrics": [extracted["metric"]],
    }
    state.update(triage_router_node(state))
    assert len(state["suspicious_items"]) >= 8
    assert len(state["auto_approved_items"]) >= 5

    state.update(planner_executor_node(state))
    assert len(state["glosas_sugeridas"]) == 8

    state.update(critic_node(state))
    assert state["critic_review"]["approved"] is True
    assert state["critic_review"]["score_conformidade"] == 1.0


def test_critic_rejects_hallucinated_glosa():
    """Garante que o nó Critic reprova glosa sem código TUSS exato ou sem cláusula contratual."""
    bad_glosa = [
        {
            "item_id": "001",
            "codigo_tuss": "10101012",
            "descricao": "Consulta",
            "tipo_anomalia": "DUPLICIDADE",
            "valor_cobrado": 250.0,
            "valor_glosado": 250.0,
            "valor_aprovado": 0.0,
            "clausula_contratual": "Sem referência",
            "justificativa_tecnica": "Glosa aplicada por consulta repetida.",
            "evidencia_banco_ou_laudo": "Histórico",
        }
    ]
    check = _deterministic_critic_verification(bad_glosa, {"rules": []})
    assert check["approved"] is False
    assert "001" in check["itens_reprovados"]


def test_nosql_store_and_dpo_dataset(tmp_path):
    """Valida a persistência NoSQL (TinyDB DynamoDB-style) e gravação da coleção DPO."""
    store = NoSQLAuditStore(db_path=tmp_path / "test_nosql.json")
    store.save_session_state("thread-123", "WAITING_HITL", {"foo": "bar"})
    loaded = store.get_session_state("thread-123")
    assert loaded is not None
    assert loaded["PK"] == "SESSION#thread-123"
    assert loaded["status"] == "WAITING_HITL"

    dpo = store.save_dpo_preference_pair(
        thread_id="thread-123",
        auditor_id="auditor@arvo.com",
        action="EDIT",
        prompt_context={"header": {"numero_guia": "2026.10.884920-4"}},
        agent_suggestion={"glosas": [{"codigo_tuss": "10101012", "valor_glosado": 250.0}]},
        human_final_decision={"glosas": [{"codigo_tuss": "10101012", "valor_glosado": 200.0}]},
    )
    assert dpo["PK"].startswith("DPO#")
    assert "prompt_context" in dpo
    assert "chosen" in dpo
    assert "rejected" in dpo
    assert len(store.list_dpo_dataset()) == 1


def test_fastapi_analyze_and_hitl_end_to_end():
    """Testa o fluxo completo via API: POST /analyze (até interrupt HITL) e POST /hitl/{thread_id} (DPO)."""
    client = TestClient(app)

    ui_resp = client.get("/")
    assert ui_resp.status_code == 200
    assert "Arvo Audit AI" in get_single_page_ui_html()

    with PDF_PATH.open("rb") as pdf_file:
        resp_analyze = client.post(
            "/analyze",
            files={"file": ("guia_tiss_auditoria_arvo_teste.pdf", pdf_file, "application/pdf")},
        )
    assert resp_analyze.status_code == 200
    data_analyze = resp_analyze.json()

    thread_id = data_analyze["thread_id"]
    assert data_analyze["status"] == "WAITING_HITL"
    assert len(data_analyze["glosas_sugeridas"]) == 8
    assert data_analyze["resumo_financeiro"]["valor_total_faturado"] == 29569.0
    assert data_analyze["resumo_financeiro"]["valor_total_glosado"] == 19680.0
    assert data_analyze["resumo_financeiro"]["valor_total_aprovado"] == 9889.0
    assert len(data_analyze["metrics"]) >= 4

    # Simula edição humana no HITL para validar geração do par DPO (chosen vs rejected)
    edited_glosas = data_analyze["glosas_sugeridas"]
    edited_glosas[0]["justificativa_tecnica"] += " [Revisado e ratificado pelo Auditor Médico Chefe]."

    resp_hitl = client.post(
        f"/hitl/{thread_id}",
        json={
            "action": "EDIT",
            "auditor_id": "dr.auditor@saudeplena.com.br",
            "chosen_glosas": edited_glosas,
            "auditor_notes": "Glosas confirmadas após conferência do prontuário e histórico SQL.",
        },
    )
    assert resp_hitl.status_code == 200
    data_hitl = resp_hitl.json()
    assert data_hitl["status"] == "COMPLETED"
    assert data_hitl["action"] == "EDIT"
    assert data_hitl["dpo_record_id"].startswith("dpo-")
    assert "chosen" in data_hitl["dpo_pair_preview"]
    assert "rejected" in data_hitl["dpo_pair_preview"]
