from contextlib import asynccontextmanager
import os
import shutil
from pathlib import Path
from typing import Any, AsyncIterator, Dict, List, Optional

from fastapi import FastAPI, File, Form, HTTPException, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import HTMLResponse

from src.graph.graph import resume_audit_from_hitl, run_audit_until_hitl
from src.models.schemas import (
    AnalyzeResponse,
    ExecutionMetric,
    GlosaSuggestion,
    HITLDecisionRequest,
    HITLResponse,
)
from src.ui import get_single_page_ui_html
from src.utils.db_manager import init_sqlite_db
from src.utils.nosql_store import NoSQLAuditStore

BASE_DIR = Path(__file__).resolve().parents[1]
UPLOAD_DIR = BASE_DIR / "data" / "uploads"
DEFAULT_PDF_CANDIDATES = [
    BASE_DIR / "guia_tiss_auditoria_arvo_teste.pdf",
    BASE_DIR / "Guia TISS e Fatura Hospitalar Sintética para Teste de Auditoria.pdf",
]

@asynccontextmanager
async def lifespan(_app: FastAPI) -> AsyncIterator[None]:
    init_sqlite_db()
    UPLOAD_DIR.mkdir(parents=True, exist_ok=True)
    yield


app = FastAPI(
    title="Arvo Medical Audit Multi-Agent System",
    description=(
        "Sistema Multiagente de Auditoria de Contas Médicas TISS/TUSS com "
        "Docling, LangGraph, LiteLLM, FastMCP, HITL Interrupt e Dataset DPO em NoSQL."
    ),
    version="1.0.0",
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


def _resolve_default_pdf() -> Path:
    for candidate in DEFAULT_PDF_CANDIDATES:
        if candidate.exists():
            return candidate
    raise FileNotFoundError(
        "Arquivo guia_tiss_auditoria_arvo_teste.pdf não encontrado na raiz do projeto."
    )


@app.get("/", response_class=HTMLResponse)
@app.get("/ui", response_class=HTMLResponse)
def serve_ui() -> HTMLResponse:
    """Serve a interface visual Single-Page Application (HTML/JS)."""
    return HTMLResponse(content=get_single_page_ui_html())


@app.get("/health")
def health_check() -> Dict[str, Any]:
    db_path = init_sqlite_db()
    return {
        "status": "ok",
        "sqlite_db": str(db_path.name),
        "default_pdf_ready": any(p.exists() for p in DEFAULT_PDF_CANDIDATES),
    }


@app.post("/analyze", response_model=AnalyzeResponse)
async def analyze_medical_guide(
    file: Optional[UploadFile] = File(default=None),
    gemini_api_key: Optional[str] = Form(default=None),
) -> AnalyzeResponse:
    """
    Recebe o PDF da Guia TISS (ou utiliza o arquivo padrão `@guia_tiss_auditoria_arvo_teste.pdf`),
    executa a extração estruturada via Docling e orquestra o grafo LangGraph
    (Triage Router -> Planner/Executor via MCP -> Critic) até a interrupção no nó HITL.
    """
    if gemini_api_key and gemini_api_key.strip():
        os.environ["GEMINI_API_KEY"] = gemini_api_key.strip()

    UPLOAD_DIR.mkdir(parents=True, exist_ok=True)
    if file and file.filename:
        target_pdf = UPLOAD_DIR / file.filename
        with target_pdf.open("wb") as buffer:
            shutil.copyfileobj(file.file, buffer)
    else:
        target_pdf = _resolve_default_pdf()

    state = run_audit_until_hitl(pdf_path=str(target_pdf))

    glosas_raw = state.get("glosas_sugeridas", [])
    glosas = [GlosaSuggestion(**g) for g in glosas_raw]
    metrics_raw = state.get("metrics", [])
    metrics = [ExecutionMetric(**m) for m in metrics_raw]

    total_latency_ms = round(sum(m.latency_ms for m in metrics), 2)
    total_tokens = sum(m.total_tokens for m in metrics)

    header = state.get("header", {})
    valor_total_faturado = float(header.get("valor_total_faturado", 29569.00))
    valor_total_glosado = round(sum(g.valor_glosado for g in glosas), 2)
    valor_total_aprovado = round(max(0.0, valor_total_faturado - valor_total_glosado), 2)

    suspicious = state.get("suspicious_items", [])
    auto_approved = state.get("auto_approved_items", [])

    return AnalyzeResponse(
        thread_id=state["thread_id"],
        status=state.get("status", "WAITING_HITL"),
        header=header,
        triage_summary={
            "total_items": len(state.get("items", [])),
            "suspicious_count": len(suspicious),
            "auto_approved_count": len(auto_approved),
            "triage_results": state.get("triage_results", []),
        },
        glosas_sugeridas=glosas,
        parecer_agente=state.get("parecer_agente", ""),
        critic_review=state.get("critic_review", {}),
        resumo_financeiro={
            "valor_total_faturado": valor_total_faturado,
            "valor_total_glosado": valor_total_glosado,
            "valor_total_aprovado": valor_total_aprovado,
        },
        metrics=metrics,
        total_latency_ms=total_latency_ms,
        total_tokens=total_tokens,
    )


@app.post("/hitl/{thread_id}", response_model=HITLResponse)
async def submit_hitl_decision(
    thread_id: str,
    decision: HITLDecisionRequest,
) -> HITLResponse:
    """
    Recebe a deliberação do auditor humano (APPROVE, EDIT ou REJECT),
    retoma a execução do LangGraph a partir do `interrupt` identificado por `thread_id`,
    finaliza o parecer de auditoria e persiste a tupla `(prompt_context, chosen, rejected)`
    na coleção DPO do banco NoSQL.
    """
    try:
        final_state = resume_audit_from_hitl(
            thread_id=thread_id,
            decision_payload=decision.model_dump(),
        )
    except KeyError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc

    glosas_finais_raw = final_state.get("glosas_finais", [])
    glosas_finais = [GlosaSuggestion(**g) for g in glosas_finais_raw]
    header = final_state.get("header", {})
    total_faturado = float(header.get("valor_total_faturado", 29569.00))
    total_glosado = round(sum(g.valor_glosado for g in glosas_finais), 2)
    total_aprovado = round(max(0.0, total_faturado - total_glosado), 2)

    dpo_record = final_state.get("dpo_record") or {}

    return HITLResponse(
        thread_id=thread_id,
        status=final_state.get("status", "COMPLETED"),
        action=decision.action,
        glosas_finais=glosas_finais,
        parecer_final=final_state.get("parecer_final", ""),
        resumo_financeiro_final={
            "valor_total_faturado": total_faturado,
            "valor_total_glosado": total_glosado,
            "valor_total_aprovado": total_aprovado,
        },
        dpo_record_id=str(dpo_record.get("record_id", "")),
        dpo_pair_preview={
            "PK": dpo_record.get("PK"),
            "SK": dpo_record.get("SK"),
            "action": dpo_record.get("action"),
            "auditor_id": dpo_record.get("auditor_id"),
            "created_at": dpo_record.get("created_at"),
            "prompt_context_length": len(str(dpo_record.get("prompt_context", ""))),
            "chosen": dpo_record.get("chosen"),
            "rejected": dpo_record.get("rejected"),
        },
    )


@app.get("/sessions")
def list_nosql_sessions() -> List[Dict[str, Any]]:
    store = NoSQLAuditStore()
    return store.list_sessions()


@app.get("/dpo-dataset")
def list_dpo_dataset() -> List[Dict[str, Any]]:
    store = NoSQLAuditStore()
    return store.list_dpo_dataset()
