import asyncio
import json
from typing import Any, Dict, List, Optional

try:
    from fastmcp import FastMCP
except ImportError:  # pragma: no cover
    from mcp.server.fastmcp import FastMCP  # type: ignore

from src.utils.db_manager import execute_readonly_sql, init_sqlite_db, search_tuss_guidelines

mcp = FastMCP("ArvoMedicalAuditMCP")


@mcp.tool()
def query_patient_history_sql(
    sql_query: Optional[str] = None,
    cpf: str = "123.456.789-00",
    data_referencia: str = "2026-10-18",
) -> str:
    """
    Executa consulta SQL (Text-to-SQL) no banco SQLite de auditoria médica para verificar
    histórico de procedimentos do paciente (ex: duplicidade de TUSS 10101012 nos últimos 15 dias)
    e cruzamento com a tabela contratual.
    """
    init_sqlite_db()
    if not sql_query or not sql_query.strip():
        safe_cpf = cpf.replace("'", "''")
        safe_date = data_referencia.replace("'", "''")
        sql_query = f"""
        SELECT
            h.cpf_paciente,
            p.nome AS nome_paciente,
            p.plano,
            h.codigo_tuss,
            h.descricao,
            h.data_execucao,
            CAST(julianday('{safe_date}') - julianday(h.data_execucao) AS INTEGER) AS dias_desde_ultima_execucao,
            r.janela_duplicidade_dias,
            h.guia_referencia,
            h.prestador,
            h.valor_pago,
            h.status_pagamento,
            h.observacao,
            r.clausula_contratual,
            r.diretriz_ans_tuss
        FROM historico_procedimentos_paciente h
        JOIN pacientes p ON p.cpf = h.cpf_paciente
        LEFT JOIN tabela_tuss_regras r ON r.codigo_tuss = h.codigo_tuss
        WHERE h.cpf_paciente = '{safe_cpf}'
        ORDER BY h.data_execucao DESC;
        """
    rows = execute_readonly_sql(sql_query)
    return json.dumps(
        {
            "tool": "query_patient_history_sql",
            "executed_sql": " ".join(sql_query.strip().split()),
            "row_count": len(rows),
            "results": rows,
        },
        ensure_ascii=False,
    )


@mcp.tool()
def search_tuss_rules_rag(
    query: str,
    codigos_tuss: Optional[List[str]] = None,
    top_k: int = 15,
) -> str:
    """
    Realiza busca semântica/híbrida nas diretrizes da ANS, regras de auditoria TUSS e
    tabela de preços contratuais para validar procedimentos, diárias, taxas e OPME.
    """
    init_sqlite_db()
    rules = search_tuss_guidelines(query=query, codigos_tuss=codigos_tuss, top_k=top_k)
    return json.dumps(
        {
            "tool": "search_tuss_rules_rag",
            "query": query,
            "codigos_filtrados": codigos_tuss or [],
            "count": len(rules),
            "rules": rules,
        },
        ensure_ascii=False,
    )


def invoke_mcp_tool_sync(tool_name: str, arguments: Dict[str, Any]) -> Dict[str, Any]:
    """
    Consome a ferramenta registrada no servidor FastMCP mantendo isolamento de protocolo
    e compatibilidade síncrona/assíncrona dentro dos nós do LangGraph.
    """
    if hasattr(mcp, "_tool_manager") and hasattr(mcp._tool_manager, "get_tool"):
        tool_obj = mcp._tool_manager.get_tool(tool_name)
        if tool_obj is not None and hasattr(tool_obj, "fn"):
            raw = tool_obj.fn(**arguments)
            return json.loads(raw) if isinstance(raw, str) else raw

    if tool_name == "query_patient_history_sql":
        raw = query_patient_history_sql(**arguments)
    elif tool_name == "search_tuss_rules_rag":
        raw = search_tuss_rules_rag(**arguments)
    else:
        raise ValueError(f"Ferramenta MCP desconhecida: {tool_name}")

    if asyncio.iscoroutine(raw):
        raw = asyncio.run(raw)
    return json.loads(raw) if isinstance(raw, str) else raw


if __name__ == "__main__":
    mcp.run()
