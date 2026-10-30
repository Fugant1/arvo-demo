from typing import Any, Dict, List, Literal, Optional, TypedDict
from pydantic import BaseModel, Field


class BilledItem(BaseModel):
    item_id: str
    data: str
    tabela: str
    codigo_tuss: str
    descricao: str
    registro_anvisa: Optional[str] = None
    quantidade: int
    valor_unitario: float
    valor_total: float


class PatientHeader(BaseModel):
    numero_guia: str
    registro_ans: str
    guia_solicitacao: str
    prestador: str
    cpf_beneficiario: str
    nome_beneficiario: str
    carteirinha: str
    data_admissao: str
    data_alta: str
    carater_acomodacao: str
    cid10: str
    relatorio_clinico: str
    valor_total_faturado: float


class TriageItemDecision(BaseModel):
    item_id: str
    codigo_tuss: str
    descricao: str
    valor_total: float
    status_triagem: Literal["AUTO_APPROVED", "SUSPICIOUS_FOR_AUDIT"]
    nivel_risco: Literal["BAIXO", "MEDIO", "ALTO", "CRITICO"]
    motivo_triagem: str


class GlosaSuggestion(BaseModel):
    item_id: str
    codigo_tuss: str
    descricao: str
    tipo_anomalia: str
    valor_cobrado: float
    valor_glosado: float
    valor_aprovado: float
    clausula_contratual: str
    justificativa_tecnica: str
    evidencia_banco_ou_laudo: str


class CriticReview(BaseModel):
    approved: bool
    score_conformidade: float = Field(ge=0.0, le=1.0)
    itens_reprovados: List[str] = Field(default_factory=list)
    feedback_correcao: str


class ExecutionMetric(BaseModel):
    step_name: str
    model: str
    latency_ms: float
    prompt_tokens: int
    completion_tokens: int
    total_tokens: int


class HITLDecisionRequest(BaseModel):
    action: Literal["APPROVE", "EDIT", "REJECT"] = "APPROVE"
    auditor_id: str = "auditor.chefe@saudeplena.com.br"
    chosen_glosas: Optional[List[GlosaSuggestion]] = None
    chosen_summary: Optional[str] = None
    auditor_notes: Optional[str] = None


class AnalyzeResponse(BaseModel):
    thread_id: str
    status: str
    header: Dict[str, Any]
    triage_summary: Dict[str, Any]
    glosas_sugeridas: List[GlosaSuggestion]
    parecer_agente: str
    critic_review: Dict[str, Any]
    resumo_financeiro: Dict[str, float]
    metrics: List[ExecutionMetric]
    total_latency_ms: float
    total_tokens: int


class HITLResponse(BaseModel):
    thread_id: str
    status: str
    action: str
    glosas_finais: List[GlosaSuggestion]
    parecer_final: str
    resumo_financeiro_final: Dict[str, float]
    dpo_record_id: str
    dpo_pair_preview: Dict[str, Any]


class AuditGraphState(TypedDict, total=False):
    thread_id: str
    pdf_path: str
    extracted_markdown: str
    extracted_json: Dict[str, Any]
    header: Dict[str, Any]
    items: List[Dict[str, Any]]
    triage_results: List[Dict[str, Any]]
    suspicious_items: List[Dict[str, Any]]
    auto_approved_items: List[Dict[str, Any]]
    mcp_evidence: Dict[str, Any]
    glosas_sugeridas: List[Dict[str, Any]]
    parecer_agente: str
    critic_review: Dict[str, Any]
    critic_iterations: int
    human_decision: Optional[Dict[str, Any]]
    glosas_finais: List[Dict[str, Any]]
    parecer_final: str
    dpo_record: Optional[Dict[str, Any]]
    status: str
    metrics: List[Dict[str, Any]]
