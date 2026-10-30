import math
import re
import sqlite3
from pathlib import Path
from typing import Any, Dict, List, Optional

BASE_DIR = Path(__file__).resolve().parents[2]
SQL_SEED_PATH = BASE_DIR / "migrations" / "DB_BASE.sql"
DEFAULT_DB_PATH = BASE_DIR / "data" / "arvo_audit.db"


def init_sqlite_db(db_path: Path = DEFAULT_DB_PATH, force_reset: bool = False) -> Path:
    """Inicializa o banco SQLite a partir do script migrations/DB_BASE.sql."""
    db_path.parent.mkdir(parents=True, exist_ok=True)
    need_seed = force_reset or not db_path.exists()

    if not need_seed:
        with sqlite3.connect(str(db_path)) as conn:
            cursor = conn.cursor()
            cursor.execute(
                "SELECT name FROM sqlite_master WHERE type='table' AND name='tabela_tuss_regras';"
            )
            if cursor.fetchone() is None:
                need_seed = True

    if need_seed:
        sql_script = SQL_SEED_PATH.read_text(encoding="utf-8")
        with sqlite3.connect(str(db_path)) as conn:
            conn.executescript(sql_script)
            conn.commit()

    return db_path


def execute_readonly_sql(
    sql_query: str, db_path: Path = DEFAULT_DB_PATH
) -> List[Dict[str, Any]]:
    """Executa consultas SELECT geradas via Text-to-SQL com trava de segurança read-only."""
    init_sqlite_db(db_path)
    cleaned = sql_query.strip()
    if not cleaned.upper().startswith("SELECT") and not cleaned.upper().startswith("WITH"):
        raise ValueError("Apenas consultas SELECT/WITH são permitidas no servidor MCP de auditoria.")

    forbidden = re.compile(r"\b(DROP|DELETE|UPDATE|INSERT|ALTER|ATTACH|PRAGMA)\b", re.IGNORECASE)
    if forbidden.search(cleaned):
        raise ValueError("Operação de escrita bloqueada na camada de segurança Text-to-SQL.")

    with sqlite3.connect(f"file:{db_path}?mode=ro", uri=True) as conn:
        conn.row_factory = sqlite3.Row
        cursor = conn.cursor()
        cursor.execute(cleaned)
        rows = cursor.fetchall()
        return [dict(row) for row in rows]


def _tokenize(text: str) -> List[str]:
    return re.findall(r"[a-zA-Z0-9À-ÿ]+", text.lower())


def search_tuss_guidelines(
    query: str,
    codigos_tuss: Optional[List[str]] = None,
    top_k: int = 15,
    db_path: Path = DEFAULT_DB_PATH,
) -> List[Dict[str, Any]]:
    """
    Busca híbrida (Exact TUSS Code Match + Similaridade Léxica/Semântica TF-IDF)
    sobre as diretrizes da ANS e cláusulas contratuais armazenadas no banco.
    """
    init_sqlite_db(db_path)
    with sqlite3.connect(str(db_path)) as conn:
        conn.row_factory = sqlite3.Row
        cursor = conn.cursor()
        cursor.execute("SELECT * FROM tabela_tuss_regras;")
        all_rules = [dict(r) for r in cursor.fetchall()]

    code_set = {str(c).strip() for c in (codigos_tuss or []) if str(c).strip()}
    for token in _tokenize(query):
        if token.isdigit() and len(token) == 8:
            code_set.add(token)

    query_tokens = _tokenize(query)
    scored_results: List[tuple[float, Dict[str, Any]]] = []

    for rule in all_rules:
        doc_text = (
            f"{rule['codigo_tuss']} {rule['descricao']} {rule['categoria']} "
            f"{rule['clausula_contratual']} {rule['diretriz_ans_tuss']}"
        )
        doc_tokens = _tokenize(doc_text)
        doc_token_set = set(doc_tokens)

        score = 0.0
        if rule["codigo_tuss"] in code_set:
            score += 10.0

        if query_tokens and doc_token_set:
            overlap = sum(1 for t in query_tokens if t in doc_token_set)
            score += overlap / math.sqrt(len(query_tokens) * len(doc_token_set))

        rule_with_score = dict(rule)
        rule_with_score["relevance_score"] = round(score, 4)
        scored_results.append((score, rule_with_score))

    scored_results.sort(key=lambda item: item[0], reverse=True)
    filtered = [item[1] for item in scored_results if item[0] > 0]
    if not filtered:
        filtered = [item[1] for item in scored_results[:top_k]]
    return filtered[:top_k]
