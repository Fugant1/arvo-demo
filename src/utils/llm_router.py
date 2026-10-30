import json
import os
import re
import time
from typing import Any, Callable, Dict, List, Literal, Optional, Tuple
from dotenv import load_dotenv
import litellm

load_dotenv()

litellm.suppress_debug_info = True
litellm.drop_params = True

MODEL_TRIAGE_FAST = os.getenv("ARVO_FAST_MODEL", "gemini/gemini-3.5-flash-lite")
MODEL_AUDIT_REASONING = os.getenv("ARVO_REASONING_MODEL", "gemini/gemini-3.8-flash")
MODEL_AUDIT_FALLBACK = "gemini/gemini-2.5-flash"


def _extract_json_block(raw_text: str) -> Dict[str, Any]:
    cleaned = raw_text.strip()
    if cleaned.startswith("```"):
        cleaned = re.sub(r"^```(?:json)?\s*", "", cleaned)
        cleaned = re.sub(r"\s*```$", "", cleaned)
    start = cleaned.find("{")
    end = cleaned.rfind("}")
    if start != -1 and end != -1 and end > start:
        cleaned = cleaned[start : end + 1]
    return json.loads(cleaned)


def _estimate_tokens(model: str, text: str) -> int:
    try:
        return int(litellm.token_counter(model=model, text=text))
    except Exception:
        return max(1, len(text) // 4)


def call_routed_llm(
    step_name: str,
    tier: Literal["fast", "reasoning"],
    messages: List[Dict[str, str]],
    fallback_builder: Callable[[], Dict[str, Any]],
    max_completion_tokens: int = 4096,
    reasoning_effort: Optional[str] = None,
    timeout: float = 35.0,
) -> Tuple[Dict[str, Any], Dict[str, Any]]:
    """
    Roteador central LiteLLM:
    - tier='fast'      -> gemini-flash-lite (Triage Router)
    - tier='reasoning' -> gemini-flash (Planner e Critic com reasoning_effort controlado)
    Registra contagem de tokens (prompt, completion, total) e latência em ms.
    """
    primary_model = MODEL_TRIAGE_FAST if tier == "fast" else MODEL_AUDIT_REASONING
    candidate_models = (
        [primary_model]
        if tier == "fast"
        else [primary_model, MODEL_AUDIT_FALLBACK]
    )

    t0 = time.perf_counter()
    api_key = os.getenv("GEMINI_API_KEY") or os.getenv("GOOGLE_API_KEY")

    if api_key:
        for model_name in candidate_models:
            try:
                kwargs: Dict[str, Any] = {
                    "model": model_name,
                    "messages": messages,
                    "max_completion_tokens": max_completion_tokens,
                    "response_format": {"type": "json_object"},
                    "api_key": api_key,
                    "timeout": timeout,
                }
                # Controla o orçamento de raciocínio interno para evitar minutos de espera
                if reasoning_effort:
                    kwargs["reasoning_effort"] = reasoning_effort

                response = litellm.completion(**kwargs)
                latency_ms = round((time.perf_counter() - t0) * 1000.0, 2)
                content = response.choices[0].message.content or "{}"
                parsed = _extract_json_block(content)

                usage = getattr(response, "usage", None)
                prompt_tokens = getattr(usage, "prompt_tokens", 0) or _estimate_tokens(
                    model_name, json.dumps(messages, ensure_ascii=False)
                )
                completion_tokens = getattr(
                    usage, "completion_tokens", 0
                ) or _estimate_tokens(model_name, content)
                total_tokens = getattr(usage, "total_tokens", 0) or (
                    prompt_tokens + completion_tokens
                )

                metric = {
                    "step_name": step_name,
                    "model": model_name,
                    "latency_ms": latency_ms,
                    "prompt_tokens": int(prompt_tokens),
                    "completion_tokens": int(completion_tokens),
                    "total_tokens": int(total_tokens),
                }
                return parsed, metric
            except Exception:
                continue

    # Caso não haja chave GEMINI_API_KEY ativa no ambiente ou ocorra indisponibilidade de rede,
    # garante continuidade determinística mantendo a contabilização via LiteLLM token_counter.
    parsed_fallback = fallback_builder()
    fallback_str = json.dumps(parsed_fallback, ensure_ascii=False)
    prompt_str = json.dumps(messages, ensure_ascii=False)
    prompt_tokens = _estimate_tokens(primary_model, prompt_str)
    completion_tokens = _estimate_tokens(primary_model, fallback_str)
    latency_ms = round((time.perf_counter() - t0) * 1000.0, 2)

    metric = {
        "step_name": step_name,
        "model": primary_model,
        "latency_ms": latency_ms,
        "prompt_tokens": int(prompt_tokens),
        "completion_tokens": int(completion_tokens),
        "total_tokens": int(prompt_tokens + completion_tokens),
    }
    return parsed_fallback, metric
