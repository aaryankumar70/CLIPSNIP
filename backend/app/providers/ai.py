"""Provider-agnostic clip detection. LLM output is never trusted: parsed, validated, filtered, retried."""
import json, os, re
from abc import ABC, abstractmethod
from pydantic import ValidationError
from ..schemas.clip import ClipCandidate

MIN_LEN, MAX_LEN = 15.0, 90.0

SYSTEM = """You are an expert short-form video editor. Given a timestamped transcript, pick the best
self-contained moments for short clips (strong hook, standalone, insightful/emotional/funny, complete thought).
Avoid clips that start/end mid-sentence, need prior context, or are filler. Each clip must be 15-90 seconds and
start/end on sentence boundaries using the timestamps given. Score 0-100 (estimated content quality, not virality).
Reply with ONLY a JSON array, no prose, no markdown. Each item:
{"start":float,"end":float,"title":str,"hook":str,"reason":str,"score":float,
"category":"educational|funny|emotional|controversial|inspirational|storytelling|surprising|technical|opinion"}"""

class AIError(RuntimeError):
    pass

class AIProvider(ABC):
    @abstractmethod
    def complete(self, system: str, user: str) -> str: ...

class OpenAIProvider(AIProvider):
    def __init__(self, model: str | None = None):
        from openai import OpenAI
        key = os.environ.get("OPENAI_API_KEY")
        if not key: raise AIError("OPENAI_API_KEY is not set")
        self.c, self.model = OpenAI(api_key=key), model or os.environ.get("OPENAI_MODEL", "gpt-4o-mini")
    def complete(self, system, user):
        r = self.c.chat.completions.create(model=self.model, temperature=0.3,
            messages=[{"role": "system", "content": system}, {"role": "user", "content": user}])
        return r.choices[0].message.content or ""

class AnthropicProvider(AIProvider):
    def __init__(self, model: str | None = None):
        import anthropic
        key = os.environ.get("ANTHROPIC_API_KEY")
        if not key: raise AIError("ANTHROPIC_API_KEY is not set")
        self.c, self.model = anthropic.Anthropic(api_key=key), model or os.environ.get("ANTHROPIC_MODEL", "claude-sonnet-4-6")
    def complete(self, system, user):
        r = self.c.messages.create(model=self.model, max_tokens=4000, system=system,
                                   messages=[{"role": "user", "content": user}])
        return "".join(b.text for b in r.content if b.type == "text")

def get_provider(name: str) -> AIProvider:
    try:
        return {"openai": OpenAIProvider, "anthropic": AnthropicProvider}[name.lower()]()
    except KeyError:
        raise AIError(f"Unknown AI_PROVIDER '{name}' (use openai or anthropic)")

def format_transcript(segments: list[dict]) -> str:
    return "\n".join(f"[{s['start']:.1f}-{s['end']:.1f}] {s['text'].strip()}" for s in segments)

def parse_candidates(raw: str, duration: float) -> list[ClipCandidate]:
    """Extract JSON array, validate each item, drop invalid ones. Raises AIError if nothing usable."""
    m = re.search(r"\[.*\]", raw, re.S)
    if not m: raise AIError("AI response contained no JSON array")
    try: items = json.loads(m.group(0))
    except json.JSONDecodeError as e: raise AIError(f"AI returned malformed JSON: {e}")
    out = []
    for it in items if isinstance(items, list) else []:
        try: c = ClipCandidate.model_validate(it)
        except ValidationError: continue
        if c.end > duration or not (MIN_LEN <= c.end - c.start <= MAX_LEN): continue
        if any(c.start < o.end and c.end > o.start for o in out): continue  # no overlaps
        out.append(c)
    if not out: raise AIError("AI returned no valid clip candidates")
    return sorted(out, key=lambda c: -c.score)

def detect_clips(provider: AIProvider, segments: list[dict], duration: float, retries: int = 3) -> list[ClipCandidate]:
    n = max(3, min(10, int(duration // 120) + 3))
    user = f"Video duration: {duration:.0f}s. Return up to {n} clips.\n\nTRANSCRIPT:\n{format_transcript(segments)}"
    last = None
    for _ in range(retries):
        try: return parse_candidates(provider.complete(SYSTEM, user), duration)[:n]
        except AIError as e: last = e
        except Exception as e: last = AIError(f"AI API failure: {e}")
    raise AIError(f"Clip analysis failed after {retries} attempts: {last}")
