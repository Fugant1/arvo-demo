# Arvo Demo — Agente de Auditoria de Contas Médicas com Autocorreção e HITL

Sistema prototipal funcional para auditoria automatizada de contas médicas no padrão **TISS/TUSS (ANS)** utilizando **Docling**, **LangGraph**, **LiteLLM**, **FastMCP**, **SQLite** e **TinyDB (NoSQL + Dataset DPO)**.

## Arquitetura do Sistema

1. **Extração Estruturada (`src/graph/nodes/extractor.py`)**:
   - Utiliza **Docling** (`DocumentConverter`) para converter `@guia_tiss_auditoria_arvo_teste.pdf` em Markdown (`data/extracted_guia_tiss.md`) e JSON estruturado (`data/extracted_guia_tiss.json`), extraindo o cabeçalho TISS, os 15 itens faturados (Tabelas TUSS 18, 19, 20 e 22) e o Relatório Descritivo do Ato Cirúrgico.
2. **Roteamento de Modelos LiteLLM (`src/utils/llm_router.py`)**:
   - `gemini/gemini-2.5-flash-lite` para triagem inicial de baixa latência (`Triage Router`).
   - `gemini/gemini-2.5-pro` (com fallback para `gemini/gemini-2.5-flash`) para raciocínio clínico/contratual (`Planner & Executor`) e validação anti-alucinação (`Critic Node`).
   - Contabiliza tokens (`prompt_tokens`, `completion_tokens`, `total_tokens`) e latência (`latency_ms`) em cada etapa.
3. **Banco SQLite + Servidor MCP (`migrations/DB_BASE.sql`, `src/utils/db_manager.py`, `src/utils/mcp_server.py`)**:
   - Banco SQLite populado com dados do paciente CPF `123.456.789-00` (incluindo consulta `10101012` realizada há 10 dias — dentro da janela de 15 dias — e TC de Abdome `41001095` externa) e regras/preços contratuais TUSS/ANS.
   - Servidor **FastMCP** expondo `query_patient_history_sql` (Text-to-SQL read-only) e `search_tuss_rules_rag` (busca semântica/híbrida nas diretrizes ANS).
4. **Fluxo Multiagente em LangGraph (`src/graph/graph.py`)**:
   - `extractor` $\rightarrow$ `triage_router` $\rightarrow$ `planner_executor` $\rightarrow$ `critic` (loop condicional de autocorreção) $\rightarrow$ `hitl` (pausa com `interrupt` por `thread_id`).
5. **HITL + NoSQL + Dataset DPO (`src/utils/nosql_store.py`, `src/graph/nodes/hitl.py`)**:
   - Persistência de estado e logs em banco NoSQL local (`TinyDB` com modelagem `PK`/`SK` estilo DynamoDB em `data/nosql_dynamodb_store.json`).
   - Grava o par contrastivo `(prompt_context, chosen, rejected)` na coleção `dpo_preference_dataset` após a decisão humana (`APPROVE`, `EDIT` ou `REJECT`).

## Como Executar

```powershell
# 1. Inicializar servidor FastAPI + Interface Visual Single-Page (porta 8000)
.\venv\Scripts\python.exe -m uvicorn src.app:app --host 0.0.0.0 --port 8000
```

Acesse **`http://localhost:8000`** no navegador para operar visualmente:
- **Passo 1 (`POST /analyze`)**: Executa Docling + LangGraph até a interrupção do HITL.
- **Passo 2 (`POST /hitl/{thread_id}`)**: Aprova ou edita as glosas sugeridas, retoma o grafo e salva o par de preferência DPO.

## Executando os Testes Automatizados

```powershell
.\venv\Scripts\python.exe -m pytest -v
```
