import json
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional
from tinydb import Query, TinyDB

BASE_DIR = Path(__file__).resolve().parents[2]
DEFAULT_NOSQL_PATH = BASE_DIR / "data" / "nosql_dynamodb_store.json"


class NoSQLAuditStore:
    """
    Camada de persistência NoSQL orientada a documentos baseada em TinyDB,
    modelada com chaves de partição (PK) e ordenação (SK) no padrão AWS DynamoDB.
    Gerencia sessões de grafo, trilha de auditoria e dataset de preferência DPO.
    """

    def __init__(self, db_path: Path = DEFAULT_NOSQL_PATH):
        self.db_path = db_path
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self.db = TinyDB(
            str(self.db_path),
            indent=2,
            ensure_ascii=False,
            encoding="utf-8",
        )
        self.sessions_table = self.db.table("audit_sessions")
        self.logs_table = self.db.table("audit_decision_logs")
        self.dpo_table = self.db.table("dpo_preference_dataset")

    def save_session_state(
        self, thread_id: str, status: str, state_data: Dict[str, Any]
    ) -> Dict[str, Any]:
        now = datetime.now(timezone.utc).isoformat()
        pk = f"SESSION#{thread_id}"
        sk = "METADATA#CURRENT"

        compact_state = {
            k: v
            for k, v in state_data.items()
            if k not in ("extracted_markdown", "extracted_json")
        }
        serializable_state = json.loads(
            json.dumps(compact_state, default=str, ensure_ascii=False)
        )
        item = {
            "PK": pk,
            "SK": sk,
            "thread_id": thread_id,
            "status": status,
            "updated_at": now,
            "state": serializable_state,
        }

        SessionQuery = Query()
        self.sessions_table.upsert(
            item, (SessionQuery.PK == pk) & (SessionQuery.SK == sk)
        )
        return item

    def get_session_state(self, thread_id: str) -> Optional[Dict[str, Any]]:
        pk = f"SESSION#{thread_id}"
        SessionQuery = Query()
        results = self.sessions_table.search(
            (SessionQuery.PK == pk) & (SessionQuery.SK == "METADATA#CURRENT")
        )
        return results[0] if results else None

    def list_sessions(self) -> List[Dict[str, Any]]:
        return self.sessions_table.all()

    def append_decision_log(
        self, thread_id: str, event_type: str, payload: Dict[str, Any]
    ) -> Dict[str, Any]:
        now = datetime.now(timezone.utc).isoformat()
        log_item = {
            "PK": f"SESSION#{thread_id}",
            "SK": f"LOG#{now}#{uuid.uuid4().hex[:6]}",
            "thread_id": thread_id,
            "event_type": event_type,
            "timestamp": now,
            "payload": json.loads(json.dumps(payload, default=str, ensure_ascii=False)),
        }
        self.logs_table.insert(log_item)
        return log_item

    def save_dpo_preference_pair(
        self,
        thread_id: str,
        auditor_id: str,
        action: str,
        prompt_context: Dict[str, Any],
        agent_suggestion: Dict[str, Any],
        human_final_decision: Dict[str, Any],
        naive_baseline_rejected: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        """
        Persiste a tupla (prompt_context, chosen, rejected) na coleção separada
        `dpo_preference_dataset` no formato compatível com treinamento DPO (TRL/HuggingFace).
        - Se o humano EDITOU ou REJEITOU a sugestão do agente:
          chosen = decisão humana editada; rejected = sugestão original do agente.
        - Se o humano APROVOU integralmente a sugestão do agente:
          chosen = sugestão validada do agente; rejected = baseline ingênuo sem validação
          contratual/histórico (ou rascunho pré-Critic), garantindo contraste de preferência.
        """
        record_id = f"dpo-{uuid.uuid4().hex[:12]}"
        now = datetime.now(timezone.utc).isoformat()

        prompt_str = json.dumps(prompt_context, ensure_ascii=False, indent=2)
        chosen_str = json.dumps(human_final_decision, ensure_ascii=False, indent=2)

        if action in ("EDIT", "REJECT"):
            rejected_payload = agent_suggestion
        else:
            rejected_payload = naive_baseline_rejected or {
                "glosas": [],
                "parecer": (
                    "Aprovação automática da fatura hospitalar pelo valor de face (R$ 29.569,00) "
                    "sem cruzamento de histórico SQL (TUSS 10101012 / 41001095) e sem auditoria "
                    "do relato cirúrgico (upcoding 31005128, laparotomia 31009050, UTI 60001020 e OPME 70881204)."
                ),
                "motivo_rejeicao_dpo": "Falso negativo crítico: ausência de glosa técnica e cláusula contratual ANS/TUSS.",
            }

        rejected_str = json.dumps(rejected_payload, ensure_ascii=False, indent=2)

        dpo_item = {
            "PK": f"DPO#{record_id}",
            "SK": f"SESSION#{thread_id}",
            "record_id": record_id,
            "thread_id": thread_id,
            "auditor_id": auditor_id,
            "action": action,
            "created_at": now,
            "prompt_context": prompt_str,
            "chosen": chosen_str,
            "rejected": rejected_str,
            "metadata": {
                "guia_numero": prompt_context.get("header", {}).get("numero_guia", ""),
                "cpf_beneficiario": prompt_context.get("header", {}).get("cpf_beneficiario", ""),
                "num_glosas_chosen": len(human_final_decision.get("glosas", [])),
            },
        }
        self.dpo_table.insert(dpo_item)
        return dpo_item

    def list_dpo_dataset(self) -> List[Dict[str, Any]]:
        return self.dpo_table.all()
