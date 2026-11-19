"""Provider-agnostic clip detection, windowed sentence analysis, scoring, and metadata generation."""
import json
import math
import os
import re
import wave
from abc import ABC, abstractmethod
from pathlib import Path
from typing import Any, Callable
import httpx
import numpy as np
from pydantic import BaseModel, Field, ValidationError

from ..config import (
    DEFAULT_FOOTER_TEMPLATE,
    DEFAULT_HASHTAGS,
    DEFAULT_TAGS,
    IDEAL_CLIP_MAX_S,
    IDEAL_CLIP_MIN_S,
    MAX_CLIP_S,
    MAX_FIRST_THIRD_RATIO,
    MAX_WINDOWS,
    MIN_CLIP_GAP_S,
    MIN_CLIP_S,
    WEIGHT_AUDIO,
    WEIGHT_HOOK,
    WEIGHT_LLM,
    WEIGHT_STANDALONE,
    WINDOW_OVERLAP_S,
    WINDOW_S,
    calculate_clip_count,
    get_settings,
)
from ..models import db
from ..schemas.clip import ClipCandidate

SYSTEM_WINDOW_CLIPS = """You are an expert viral editor for YouTube Shorts and TikTok.
Find the most ENTERTAINING, FUNNY, DRAMATIC, or VIRAL moments in this numbered transcript like [12] text.

Choose runs of consecutive sentences (20-60 seconds long) that:
(a) Open with an immediate irresistible hook in the first sentence (curiosity, bold claim, question, hilarious reaction, or shocking statement);
(b) Are packed with fun, humor, high energy, unexpected twists, heated debate, or high retention moments;
(c) End on a punchline, laugh, climax, or satisfying conclusion without trailing off into boring filler;
(d) Make standalone sense with zero prior context.

Reject slow explanations, monologues, sponsor reads, intro chit-chat, and boring segments.

Return JSON only:
{"clips":[{"start_sentence":int,"end_sentence":int,"title":str (punchy viral title, max 8 words),
"hook_reason":str,"standalone":bool,"score":int 1-10,"category":str (funny|dramatic|twist|fail|epic|mindblown)}]}.
Fewer punchy, laugh-out-loud clips are much better than weak filler.
10=viral gold, 8=super entertaining/funny, 5 or below=skip."""

SYSTEM_METADATA = """You write high-CTR YouTube Shorts metadata for a vertical video clip.
Requirements:
1. Title: max 90 characters, punchy curiosity-inducing title with 1-2 relevant emojis (e.g. Bro Did NOT Expect This... 😭, Wait Until The End 💀).
2. Description: 3 short engaging lines summarizing the hook and punchline, plus an invitation to subscribe/comment.
3. Tags: an array of exactly 8 relevant viral tags (no '<' or '>', max 500 characters total).
Return JSON only: {"title": str, "description": str, "tags": [str]}"""

CLIPS_SCHEMA = {
    "type": "object",
    "properties": {
        "clips": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "start_sentence": {"type": "integer"},
                    "end_sentence": {"type": "integer"},
                    "title": {"type": "string"},
                    "hook_reason": {"type": "string"},
                    "standalone": {"type": "boolean"},
                    "score": {"type": "integer"},
                },
                "required": ["start_sentence", "end_sentence", "title", "score"],
            },
        }
    },
    "required": ["clips"],
}

METADATA_SCHEMA = {
    "type": "object",
    "properties": {
        "title": {"type": "string"},
        "description": {"type": "string"},
        "tags": {
            "type": "array",
            "items": {"type": "string"},
        },
    },
    "required": ["title", "description", "tags"],
}

class AIError(RuntimeError):
    pass

class AIProvider(ABC):
    @abstractmethod
    def complete(self, system: str, user: str, *args, **kwargs) -> str:
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

    def complete(self, system: str, user: str, *args, **kwargs) -> str:
        format_schema = kwargs.get("format_schema")
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

    def complete(self, system: str, user: str, *args, **kwargs) -> str:
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

    def complete(self, system: str, user: str, *args, **kwargs) -> str:
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

# ----------------- Windowing and Heuristics -----------------

SPONSOR_PATTERNS = [
    r"\bsponsor",
    r"\bsponsored by",
    r"\bpatreon\b",
    r"\bsubscribe\b",
    r"\blink in (the )?description\b",
    r"\buse code\b",
    r"\bdiscount code\b",
    r"\bmerch\b",
    r"\bcheck out the link\b",
]

FILLER_STARTS = {"um", "uh", "so", "like", "well", "actually", "yeah", "okay", "alright"}

HOOK_WORDS = {
    "secret", "never", "why", "insane", "truth", "shocking", "best", "worst",
    "unbelievable", "huge", "warning", "revealed", "finally", "crazy", "impossible",
    "bro", "wait", "what", "no", "omg", "shut", "dude", "literally", "died",
    "fail", "caught", "hilarious", "laugh", "wtf", "cooked", "nah", "crying",
    "lost", "winner", "epic", "stop", "swear", "look", "watch"
}

def score_window_heuristic(window_sentences: list[dict[str, Any]]) -> float:
    """Pre-score a sentence window: speech rate, questions, exclamations, humor/hook cues, minus sponsor penalty."""
    if not window_sentences:
        return 0.0

    duration = max(1.0, window_sentences[-1]["end"] - window_sentences[0]["start"])
    total_words = sum(len(s.get("words", [])) for s in window_sentences)
    speech_rate = min(3.5, total_words / duration)

    questions = sum(1 for s in window_sentences if s.get("text", "").strip().endswith("?"))
    exclamations = sum(1 for s in window_sentences if s.get("text", "").strip().endswith("!"))

    full_text = " ".join(s.get("text", "") for s in window_sentences).lower()
    sponsor_hits = sum(1 for p in SPONSOR_PATTERNS if re.search(p, full_text))
    hook_word_hits = sum(1 for w in HOOK_WORDS if re.search(rf"\b{w}\b", full_text))
    laughter_hits = sum(1 for p in [r"\blol\b", r"\blmao\b", r"\bhaha\b", r"\[laughter\]", r"\[laughs\]"] if re.search(p, full_text))

    score = (
        (speech_rate * 2.0)
        + (questions * 1.5)
        + (exclamations * 1.2)
        + (min(5, hook_word_hits) * 0.8)
        + (min(3, laughter_hits) * 2.0)
        - (sponsor_hits * 5.0)
    )
    return max(0.0, score)

def build_windows(
    sentences: list[dict[str, Any]],
    window_s: int = WINDOW_S,
    overlap_s: int = WINDOW_OVERLAP_S,
    max_windows: int = MAX_WINDOWS,
) -> list[list[dict[str, Any]]]:
    """Slice sentences into overlapping time windows, pre-scoring to keep top max_windows."""
    if not sentences:
        return []

    total_duration = sentences[-1]["end"]
    step_s = max(30, window_s - overlap_s)
    raw_windows: list[list[dict[str, Any]]] = []

    t = 0.0
    while t < total_duration:
        w_end = t + window_s
        w_sents = [s for s in sentences if s["start"] < w_end and s["end"] > t]
        if w_sents:
            raw_windows.append(w_sents)
        t += step_s

    if len(raw_windows) <= max_windows:
        return raw_windows

    # Pre-score and keep top max_windows, preserved in chronological order
    scored = [(score_window_heuristic(w), idx, w) for idx, w in enumerate(raw_windows)]
    scored.sort(key=lambda x: -x[0])
    selected = scored[:max_windows]
    selected.sort(key=lambda x: x[1])
    return [item[2] for item in selected]

# ----------------- Audio Energy and Features -----------------

def compute_audio_features(wav_path: Path | None, start: float, end: float) -> tuple[float, float]:
    """Calculate RMS energy and silence ratio from 16kHz mono WAV."""
    if not wav_path or not wav_path.is_file():
        return 0.5, 0.0

    try:
        with wave.open(str(wav_path), "rb") as wf:
            rate = wf.getframerate()
            start_frame = int(start * rate)
            end_frame = int(end * rate)
            n_frames = max(1, end_frame - start_frame)
            wf.setpos(min(start_frame, max(0, wf.getnframes() - 1)))
            raw = wf.readframes(n_frames)
            samples = np.frombuffer(raw, dtype=np.int16).astype(np.float32)
            if len(samples) == 0:
                return 0.5, 0.0
            samples /= 32768.0
            rms = float(np.sqrt(np.mean(samples**2)))
            energy = min(1.0, rms * 5.0)
            silence_ratio = float(np.mean(np.abs(samples) < 0.015))
            return energy, silence_ratio
    except Exception:
        return 0.5, 0.0

def compute_hook_features(first_sent_text: str, first_words: list[dict[str, Any]]) -> tuple[float, float]:
    """Returns (hook_score, filler_penalty) for the first 3 seconds / first sentence."""
    text_lower = first_sent_text.strip().lower()
    score = 0.0

    if "?" in text_lower:
        score += 0.25
    if re.search(r"\b\d+\b", text_lower):
        score += 0.25
    if re.search(r"\b(you|your|you're)\b", text_lower):
        score += 0.25
    if any(re.search(rf"\b{w}\b", text_lower) for w in HOOK_WORDS):
        score += 0.25

    # Check for leading filler words
    filler_penalty = 0.0
    if first_words:
        first_w = re.sub(r"[^\w]", "", first_words[0]["word"]).lower()
        if first_w in FILLER_STARTS:
            filler_penalty = 0.15

    return min(1.0, score), filler_penalty

# ----------------- Candidate Extraction and Scoring -----------------

def parse_window_candidates(
    raw: str,
    sentences_map: dict[int, dict[str, Any]],
    min_len: float = MIN_CLIP_S,
    max_len: float = MAX_CLIP_S,
    full_sentences_map: dict[int, dict[str, Any]] | None = None,
) -> list[dict[str, Any]]:
    """Parse candidate clips from LLM window response, converting sentence indices to precise timestamps."""
    m = re.search(r"\{.*\}", raw, re.S)
    if not m:
        raise AIError("Response contains no JSON object")

    try:
        data = json.loads(m.group(0))
    except Exception as e:
        raise AIError(f"Malformed JSON: {e}")

    clips_data = data.get("clips", [])
    if not isinstance(clips_data, list):
        raise AIError("'clips' must be a list")

    candidates: list[dict[str, Any]] = []
    lookup = full_sentences_map if full_sentences_map is not None else sentences_map

    for it in clips_data:
        try:
            s_idx = int(it["start_sentence"])
            e_idx = int(it["end_sentence"])
            llm_score = float(it.get("score", 7))
            title = str(it.get("title", ""))[:80]
            hook_reason = str(it.get("hook_reason", ""))
            standalone = bool(it.get("standalone", True))
            category = str(it.get("category", it.get("entertainment_type", "funny")))
        except (KeyError, ValueError, TypeError):
            continue

        if s_idx not in sentences_map or e_idx not in lookup or e_idx < s_idx:
            continue

        s_sent = sentences_map[s_idx]
        e_sent = lookup[e_idx]

        if not s_sent.get("words") or not e_sent.get("words"):
            continue

        start_time = max(0.0, s_sent["words"][0]["start"] - 0.15)
        end_time = e_sent["words"][-1]["end"] + 0.4
        duration = end_time - start_time

        # If LLM picked a short hook dialogue (duration < min_len), expand end forward along sentences
        curr_e = e_idx
        while duration < min_len and (curr_e + 1) in lookup:
            next_sent = lookup[curr_e + 1]
            if not next_sent.get("words"):
                break
            next_end = next_sent["words"][-1]["end"] + 0.4
            if next_end - start_time > max_len:
                break
            curr_e += 1
            e_sent = next_sent
            end_time = next_end
            duration = end_time - start_time

        # If still shorter than min_len, expand start backward if possible
        curr_s = s_idx
        while duration < min_len and (curr_s - 1) in lookup:
            prev_sent = lookup[curr_s - 1]
            if not prev_sent.get("words"):
                break
            prev_start = max(0.0, prev_sent["words"][0]["start"] - 0.15)
            if (end_time - prev_start) > max_len:
                break
            curr_s -= 1
            s_sent = prev_sent
            start_time = prev_start
            duration = end_time - start_time

        # If candidate duration is longer than max_len, trim end backward
        while duration > max_len and curr_e > curr_s:
            curr_e -= 1
            e_sent = lookup[curr_e]
            if not e_sent.get("words"):
                continue
            end_time = e_sent["words"][-1]["end"] + 0.4
            duration = end_time - start_time

        if not (min_len <= duration <= max_len):
            continue

        s_idx = curr_s
        e_idx = curr_e

        # Collect text of the clip
        clip_sents = [lookup[i] for i in range(s_idx, e_idx + 1) if i in lookup]
        clip_text = " ".join(cs.get("text", "") for cs in clip_sents)
        first_sent_text = s_sent.get("text", "")
        first_words = s_sent.get("words", [])

        candidates.append({
            "start_sentence": s_idx,
            "end_sentence": e_idx,
            "start": round(start_time, 2),
            "end": round(end_time, 2),
            "duration": round(duration, 2),
            "title": title,
            "hook_reason": hook_reason,
            "category": category,
            "standalone": standalone,
            "llm_score": llm_score,
            "text": clip_text,
            "first_sent_text": first_sent_text,
            "first_words": first_words,
        })

    return candidates

def score_clip(
    candidate: dict[str, Any],
    wav_path: Path | None = None,
) -> float:
    """Calculate final composite score (0-100 scale):

    0.5*llm/10 + 0.2*audio_energy + 0.15*hook + 0.15*standalone
    minus penalties for duration outside 75-100s, leading filler, silence > 25%.
    """
    llm_part = max(0.0, min(1.0, candidate["llm_score"] / 10.0))
    energy, silence_ratio = compute_audio_features(wav_path, candidate["start"], candidate["end"])
    hook_score, filler_penalty = compute_hook_features(candidate["first_sent_text"], candidate["first_words"])
    standalone_score = 1.0 if candidate["standalone"] else 0.0

    # Penalties
    dur = candidate["duration"]
    dur_penalty = 0.0
    if dur < IDEAL_CLIP_MIN_S:
        dur_penalty = min(0.20, (IDEAL_CLIP_MIN_S - dur) / max(1.0, IDEAL_CLIP_MIN_S) * 0.15)
    elif dur > IDEAL_CLIP_MAX_S:
        dur_penalty = min(0.20, (dur - IDEAL_CLIP_MAX_S) / max(1.0, (MAX_CLIP_S - IDEAL_CLIP_MAX_S)) * 0.15)

    silence_penalty = 0.20 if silence_ratio > 0.25 else 0.0

    final_val = (
        WEIGHT_LLM * llm_part
        + WEIGHT_AUDIO * energy
        + WEIGHT_HOOK * hook_score
        + WEIGHT_STANDALONE * standalone_score
        - dur_penalty
        - filler_penalty
        - silence_penalty
    )

    final_val = max(0.0, min(1.0, final_val))
    return round(final_val * 100.0, 1)

def select_clips(
    candidates: list[dict[str, Any]],
    video_duration: float,
    target_count: int,
    min_gap_s: float = MIN_CLIP_GAP_S,
    wav_path: Path | None = None,
) -> list[dict[str, Any]]:
    """Greedy selection of non-overlapping clips sorted by final score descending."""
    if not candidates:
        return []

    # Score each candidate
    for c in candidates:
        if "final_score" not in c:
            c["final_score"] = score_clip(c, wav_path)

    # Sort by final score descending FIRST
    candidates.sort(key=lambda c: -c["final_score"])

    first_third_limit = video_duration / 3.0 if video_duration > 0 else float("inf")
    max_first_third = max(1, math.floor(target_count * MAX_FIRST_THIRD_RATIO))

    def _try_select(allow_relax_first_third: bool, gap: float) -> list[dict[str, Any]]:
        selected: list[dict[str, Any]] = []
        first_third_count = 0

        for c in candidates:
            if len(selected) >= target_count:
                break

            in_first_third = c["start"] < first_third_limit
            if in_first_third and not allow_relax_first_third and first_third_count >= max_first_third:
                continue

            # Check overlap with existing selected clips with minimum gap
            has_overlap = any(
                not (c["end"] + gap <= s["start"] or c["start"] >= s["end"] + gap)
                for s in selected
            )
            if has_overlap:
                continue

            selected.append(c)
            if in_first_third:
                first_third_count += 1

        return selected

    # Round 1: strict first-third quota and full gap
    selected = _try_select(allow_relax_first_third=False, gap=min_gap_s)

    # Round 2: relax first-third quota if needed
    if len(selected) < target_count:
        selected = _try_select(allow_relax_first_third=True, gap=min_gap_s)

    # Round 3: relax gap to 5s if still fewer
    if len(selected) < target_count:
        selected = _try_select(allow_relax_first_third=True, gap=max(3.0, min_gap_s / 2.0))

    # Sort final selected clips chronologically for rendering and display
    selected.sort(key=lambda c: c["start"])
    return selected

# ----------------- Metadata Generation -----------------

class ClipMetaResponse(BaseModel):
    title: str = Field(min_length=1, max_length=90)
    description: str
    tags: list[str]

def generate_clip_metadata(
    provider: AIProvider,
    clip_text: str,
    source_title: str = "",
    channel_name: str = "",
    video_url: str = "",
    default_tags: list[str] | None = None,
    default_hashtags: list[str] | None = None,
    footer_template: str = DEFAULT_FOOTER_TEMPLATE,
) -> dict[str, Any]:
    """Generate title, 3-line description, and 8 tags for a clip using the local LLM."""
    tags_list = default_tags or DEFAULT_TAGS
    hashtags_list = default_hashtags or DEFAULT_HASHTAGS

    prompt = f"VIDEO TITLE: {source_title}\nCHANNEL: {channel_name}\nCLIP TRANSCRIPT:\n{clip_text}"

    def _validate(raw: str) -> dict[str, Any]:
        m = re.search(r"\{.*\}", raw, re.S)
        if not m:
            raise ValueError("No JSON object found")
        data = json.loads(m.group(0))
        title = str(data.get("title", "")).strip().replace("\n", " ")[:90]
        desc = str(data.get("description", "")).strip()
        tags = [re.sub(r"[<>]", "", str(t)).strip() for t in data.get("tags", []) if str(t).strip()]
        if not title:
            raise ValueError("Missing title")
        return {"title": title, "description": desc, "tags": tags[:8]}

    try:
        result = provider.chat_with_retry(
            system=SYSTEM_METADATA,
            user=prompt,
            validator=_validate,
            format_schema=METADATA_SCHEMA,
            max_retries=3,
        )
    except Exception:
        # Fallback metadata template
        fallback_title = clip_text[:80].strip() or "Interesting Moment"
        fallback_desc = f"Key moment from {source_title or 'the video'}.\nWatch the full context.\nSubscribe for more daily clips!"
        result = {
            "title": fallback_title[:90],
            "description": fallback_desc,
            "tags": tags_list[:8],
        }

    # Format description footer
    footer = footer_template.format(
        source_title=source_title or "Original Video",
        channel=channel_name or "Creator",
        source_url=video_url or "",
    )
    hashtags_str = " ".join(hashtags_list)
    full_description = f"{result['description']}\n\n{footer}\n\n{hashtags_str}".strip()

    # Ensure tags are formatted cleanly
    tags_final = result.get("tags") or tags_list[:8]
    if len(tags_final) < 8:
        for t in tags_list:
            if t not in tags_final:
                tags_final.append(t)
            if len(tags_final) == 8:
                break

    tags_clean = [t.replace("<", "").replace(">", "").strip() for t in tags_final[:8]]

    return {
        "title": result["title"][:90],
        "description": full_description,
        "tags": ", ".join(tags_clean)[:490],
    }

# ----------------- Full Pipeline Clip Detection -----------------

def generate_heuristic_candidates(
    sentences: list[dict[str, Any]],
    min_clip_s: int = MIN_CLIP_S,
    max_clip_s: int = MAX_CLIP_S,
    target_count: int = 10,
) -> list[dict[str, Any]]:
    """Heuristic fallback to extract candidate clips if LLM produces no candidates."""
    if not sentences:
        return []

    cands: list[dict[str, Any]] = []
    i = 0
    total = len(sentences)

    while i < total:
        s_sent = sentences[i]
        if not s_sent.get("words"):
            i += 1
            continue

        start_time = max(0.0, s_sent["words"][0]["start"] - 0.15)
        j = i
        while j < total - 1:
            next_sent = sentences[j + 1]
            if not next_sent.get("words"):
                break
            dur = next_sent["words"][-1]["end"] + 0.4 - start_time
            if dur > min(max_clip_s, 85.0):
                break
            j += 1

        e_sent = sentences[j]
        if not e_sent.get("words"):
            i += 1
            continue

        end_time = e_sent["words"][-1]["end"] + 0.4
        dur = end_time - start_time

        if min_clip_s <= dur <= max_clip_s:
            clip_sents = sentences[i : j + 1]
            clip_text = " ".join(cs.get("text", "") for cs in clip_sents)
            title = clip_text[:60].strip() or f"Highlight Moment {len(cands) + 1}"
            cands.append({
                "start_sentence": s_sent["i"],
                "end_sentence": e_sent["i"],
                "start": round(start_time, 2),
                "end": round(end_time, 2),
                "duration": round(dur, 2),
                "title": title,
                "hook_reason": "High interest segment",
                "standalone": True,
                "llm_score": 7.5,
                "text": clip_text,
                "first_sent_text": s_sent.get("text", ""),
                "first_words": s_sent.get("words", []),
            })
            i += max(1, (j - i) // 2)
        else:
            i += 1

    return cands

def detect_clips_windowed(
    provider: AIProvider,
    sentences: list[dict[str, Any]],
    duration: float,
    target_count: int,
    wav_path: Path | None = None,
    min_clip_s: int = MIN_CLIP_S,
    max_clip_s: int = MAX_CLIP_S,
) -> list[dict[str, Any]]:
    """Execute windowed clip candidate extraction and greedy scoring selection."""
    if not sentences:
        return []

    windows = build_windows(sentences)
    all_candidates: list[dict[str, Any]] = []
    seen_ranges: set[tuple[int, int]] = set()
    full_s_map = {s["i"]: s for s in sentences}

    for w_sents in windows:
        s_map = {s["i"]: s for s in w_sents}
        prompt_text = "\n".join(f"[{s['i']}] {s['text']}" for s in w_sents)
        user_prompt = f"Find up to 3 short clips in this transcript segment:\n\n{prompt_text}"

        def _val(raw: str) -> list[dict[str, Any]]:
            return parse_window_candidates(
                raw,
                s_map,
                min_len=min_clip_s,
                max_len=max_clip_s,
                full_sentences_map=full_s_map,
            )

        try:
            window_cands = provider.chat_with_retry(
                system=SYSTEM_WINDOW_CLIPS,
                user=user_prompt,
                validator=_val,
                format_schema=CLIPS_SCHEMA,
                max_retries=3,
            )
            for c in window_cands:
                key = (c["start_sentence"], c["end_sentence"])
                if key not in seen_ranges:
                    seen_ranges.add(key)
                    all_candidates.append(c)
        except Exception:
            continue

    if not all_candidates:
        all_candidates = generate_heuristic_candidates(
            sentences, min_clip_s=min_clip_s, max_clip_s=max_clip_s, target_count=target_count
        )

    selected = select_clips(all_candidates, duration, target_count, wav_path=wav_path)
    return selected

# Backward compatibility helper
MIN_LEN = 15.0
MAX_LEN = 120.0

def parse_candidates(raw: str, duration: float) -> list[ClipCandidate]:
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
        if c.end > duration or not (15.0 <= c.end - c.start <= MAX_LEN):
            continue
        valid_candidates.append(c)

    valid_candidates.sort(key=lambda c: -c.score)
    out: list[ClipCandidate] = []
    for c in valid_candidates:
        if any(c.start < o.end and c.end > o.start for o in out):
            continue
        out.append(c)

    if not out:
        raise AIError("AI returned no valid clip candidates")
    return out

def format_transcript(segments: list[dict]) -> str:
    return "\n".join(f"[{s['start']:.1f}-{s['end']:.1f}] {s['text'].strip()}" for s in segments)

def detect_clips(provider: AIProvider, segments: list[dict], duration: float, retries: int = 3) -> list[ClipCandidate]:
    n = max(3, min(10, int(duration // 120) + 3))
    user = f"Video duration: {duration:.0f}s. Return up to {n} clips.\n\nTRANSCRIPT:\n{format_transcript(segments)}"
    return provider.chat_with_retry(
        system=SYSTEM_WINDOW_CLIPS,
        user=user,
        validator=lambda raw: parse_candidates(raw, duration)[:n],
        max_retries=retries,
    )
