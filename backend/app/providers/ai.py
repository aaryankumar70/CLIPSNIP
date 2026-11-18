"""Provider-agnostic clip detection. Local Ollama is the default provider."""
import json
import os
import re
from abc import ABC, abstractmethod
from typing import Any, Callable
import httpx
from pydantic import ValidationError
from ..config import get_settings
from ..models import db
from ..schemas.clip import ClipCandidate

MIN_LEN, MAX_LEN = 15.0, 120.0

SYSTEM = """You are an expert short-form video editor. Given a timestamped transcript, pick the best
self-contained moments for short clips (strong hook, standalone, insightful/emotional/funny, complete thought).
Avoid clips that start/end mid-sentence, need prior context, or are filler. Each clip must be 60-120 seconds and
start/end on sentence boundaries using the timestamps given. Score 0-100 (estimated content quality, not virality).
Reply with ONLY a JSON array, no prose, no markdown. Each item:
{"start":float,"end":float,"title":str,"hook":str,"reason":str,"score":float,
"category":"educational|funny|emotional|controversial|inspirational|storytelling|surprising|technical|opinion"}"""

class AIError(RuntimeError):
    pass

class AIProvider(ABC):
    @abstractmethod
    def complete(self, system: str, user: str, format_schema: dict | None = None) -> str:
        ...

    def chat_with_retry(
        self,
        system: str,
        user: str,
        validator: Callable[[str], Any],
        format_schema: dict | None = None,
        max_retries: int = 3,
    ) -> Any:
        messages = [
            {"role": "system", "content": system},
            {"role": "user", "content": user},
        ]
        last_error = ""
        for attempt in range(max_retries):
            raw = self.complete_chat(messages, format_schema=format_schema)
            try:
                return validator(raw)
            except Exception as e:
                last_error = str(e)
                messages.append({"role": "assistant", "content": raw})
                messages.append(
                    {
                        "role": "user",
                        "content": f"The response was invalid: {last_error}. Please correct the output and return ONLY valid JSON matching the schema.",
                    }
                )
        raise AIError(f"Failed after {max_retries} attempts. Last validation error: {last_error}")

    def complete_chat(self, messages: list[dict[str, str]], format_schema: dict | None = None) -> str:
        system = next((m["content"] for m in messages if m["role"] == "system"), "")
        non_system = [m for m in messages if m["role"] != "system"]
        user_prompt = "\n\n".join(f"{m['role'].upper()}: {m['content']}" for m in non_system)
        if format_schema is not None:
            try:
                return self.complete(system, user_prompt, format_schema=format_schema)
            except TypeError:
                return self.complete(system, user_prompt)
        return self.complete(system, user_prompt)

    def unload(self) -> None:
        pass

class OllamaProvider(AIProvider):
    def __init__(
        self,
        model: str | None = None,
        base_url: str | None = None,
        num_ctx: int | None = None,
    ):
        s = get_settings()
        try:
            db_s = db.get_db_settings()
            self.model = model or db_s.ollama_model or s.ollama_model
            self.num_ctx = num_ctx or db_s.ollama_num_ctx or s.ollama_num_ctx
        except Exception:
            self.model = model or s.ollama_model
            self.num_ctx = num_ctx or s.ollama_num_ctx
        self.base_url = (base_url or s.ollama_url).rstrip("/")

    def complete(self, system: str, user: str, format_schema: dict | None = None) -> str:
        messages = [
            {"role": "system", "content": system},
            {"role": "user", "content": user},
        ]
        return self.complete_chat(messages, format_schema=format_schema)

    def complete_chat(self, messages: list[dict[str, str]], format_schema: dict | None = None) -> str:
        url = f"{self.base_url}/api/chat"
        payload = {
            "model": self.model,
            "messages": messages,
            "stream": False,
            "options": {
                "temperature": 0.2,
                "num_ctx": self.num_ctx,
            },
            "keep_alive": "10m",
        }
        if format_schema is not None:
            payload["format"] = format_schema

        try:
            with httpx.Client(timeout=120.0) as client:
                res = client.post(url, json=payload)
        except (httpx.ConnectError, httpx.ConnectTimeout) as e:
            raise AIError("Ollama is not running. Please run 'sudo systemctl enable --now ollama'") from e
        except Exception as e:
            raise AIError(f"Failed to communicate with Ollama: {e}") from e

        if res.status_code == 404:
            raise AIError(f"Ollama model '{self.model}' is missing. Please run 'ollama pull {self.model}'")

        if res.status_code != 200:
            err_text = res.text
            if "not found" in err_text.lower() or "model" in err_text.lower():
                raise AIError(f"Ollama model '{self.model}' is missing. Please run 'ollama pull {self.model}'")
            raise AIError(f"Ollama returned HTTP {res.status_code}: {err_text}")

        try:
            data = res.json()
            return data.get("message", {}).get("content", "")
        except Exception as e:
            raise AIError(f"Failed to parse Ollama response: {e}") from e

    def unload(self) -> None:
        """Unload the model from VRAM/RAM immediately."""
        url = f"{self.base_url}/api/chat"
        try:
            with httpx.Client(timeout=5.0) as client:
                client.post(url, json={"model": self.model, "keep_alive": 0})
        except Exception:
            pass

class OpenAIProvider(AIProvider):
    def __init__(self, model: str | None = None):
        from openai import OpenAI
        key = os.environ.get("OPENAI_API_KEY")
        if not key:
            raise AIError("OPENAI_API_KEY is not set")
        self.c = OpenAI(api_key=key)
        self.model = model or os.environ.get("OPENAI_MODEL", "gpt-4o-mini")

    def complete(self, system: str, user: str, format_schema: dict | None = None) -> str:
        r = self.c.chat.completions.create(
            model=self.model,
            temperature=0.3,
            messages=[{"role": "system", "content": system}, {"role": "user", "content": user}],
        )
        return r.choices[0].message.content or ""

class AnthropicProvider(AIProvider):
    def __init__(self, model: str | None = None):
        import anthropic
        key = os.environ.get("ANTHROPIC_API_KEY")
        if not key:
            raise AIError("ANTHROPIC_API_KEY is not set")
        self.c = anthropic.Anthropic(api_key=key)
        self.model = model or os.environ.get("ANTHROPIC_MODEL", "claude-3-5-sonnet-20241022")

    def complete(self, system: str, user: str, format_schema: dict | None = None) -> str:
        r = self.c.messages.create(
            model=self.model,
            max_tokens=4000,
            system=system,
            messages=[{"role": "user", "content": user}],
        )
        return "".join(b.text for b in r.content if b.type == "text")

def get_provider(name: str | None = None) -> AIProvider:
    provider_name = (name or get_settings().ai_provider).lower()
    if provider_name == "ollama":
        return OllamaProvider()
    elif provider_name == "openai":
        return OpenAIProvider()
    elif provider_name == "anthropic":
        return AnthropicProvider()
    else:
        raise AIError(f"Unknown AI_PROVIDER '{provider_name}' (use ollama, openai, or anthropic)")

def format_transcript(segments: list[dict]) -> str:
    return "\n".join(f"[{s['start']:.1f}-{s['end']:.1f}] {s['text'].strip()}" for s in segments)

def parse_candidates(raw: str, duration: float) -> list[ClipCandidate]:
    """Extract JSON array, validate each item, drop invalid ones. Raises AIError if nothing usable."""
    m = re.search(r"\[.*\]", raw, re.S)
    if not m:
        raise AIError("AI response contained no JSON array")
    try:
        items = json.loads(m.group(0))
    except json.JSONDecodeError as e:
        raise AIError(f"AI returned malformed JSON: {e}")
    if not isinstance(items, list):
        raise AIError("Expected JSON array of clip candidates")

    valid_candidates: list[ClipCandidate] = []
    for it in items:
        try:
            c = ClipCandidate.model_validate(it)
        except ValidationError:
            continue
        if c.end > duration or not (MIN_LEN <= c.end - c.start <= MAX_LEN):
            continue
        valid_candidates.append(c)

    # Sort by score descending FIRST (fixes overlap bug)
    valid_candidates.sort(key=lambda c: -c.score)
    out: list[ClipCandidate] = []
    for c in valid_candidates:
        if any(c.start < o.end and c.end > o.start for o in out):
            continue
        out.append(c)

    if not out:
        raise AIError("AI returned no valid clip candidates")
    return out

def detect_clips(provider: AIProvider, segments: list[dict], duration: float, retries: int = 3) -> list[ClipCandidate]:
    n = max(3, min(10, int(duration // 120) + 3))
    user = f"Video duration: {duration:.0f}s. Return up to {n} clips.\n\nTRANSCRIPT:\n{format_transcript(segments)}"
    return provider.chat_with_retry(
        system=SYSTEM,
        user=user,
        validator=lambda raw: parse_candidates(raw, duration)[:n],
        max_retries=retries,
    )
