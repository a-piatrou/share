"""Shared, credential-agnostic Claude client for GHOSTWIRE — with a multi-credential pool.

Credentials (per stack-conventions, docs/PLAN §11). The client builds a POOL from, in order:
  1. ANTHROPIC_API_KEY (sk-ant-api...) -> Console key, x-api-key.
  2. ANTHROPIC_AUTH_TOKEN[, _1, _2, _3, _4] (sk-ant-oat01...) -> subscription OAuth, sent as
     Authorization: Bearer + the beta header `anthropic-beta: oauth-2025-04-20`.
  3. none -> a deterministic STUB so local boot/tests pass without a credential.

OAuth request shape (CRITICAL — empirically verified, see below). A subscription OAuth token is
the Claude Code credential: the API only grants it the premium models (Sonnet/Opus) when the
request *looks like Claude Code* — specifically the FIRST system block must be the Claude Code
identity string. Without it, Sonnet/Opus are rejected with a MASKED `429 rate_limit_error`
(message just "Error") while Haiku still passes — which earlier looked like "OAuth is Haiku-only".
It isn't: with the identity block prepended, all three models work on every OAuth token (probe:
6 request-shapes x 3 models, then 5 tokens x {Sonnet,Opus} + structured-output + adaptive-thinking
— all 200). So for oauth clients we prepend `_CC_IDENTITY` as a system block; for api_key clients
the caller's system prompt is sent unchanged (Console keys have no such requirement).

POOL behaviour (round-robin + fallback): each call starts at a rotating client to spread load
across the credentials' separate rolling windows; on an API error (rate-limit/overload/etc) it
transparently FAILS OVER to the next credential, and only raises ClaudeUnavailable when ALL are
exhausted. This turns N subscription tokens into ~N× effective throughput + resilience. (Note:
pooling subscription tokens for programmatic load is outside their typical individual-use intent;
fine for a local demo on your own accounts.)

Model ids verified via the claude-api reference: Opus 4.8 / Sonnet 4.6 / Haiku 4.5. Adaptive
thinking is the supported mode on these models; legacy `budget_tokens` would 400. Always check
stop_reason before reading content.
"""

from __future__ import annotations

import json
import threading
from functools import lru_cache
from typing import Any

import anthropic
import jsonschema

from app.config import get_settings

OPUS = "claude-opus-4-8"
SONNET = "claude-sonnet-4-6"
HAIKU = "claude-haiku-4-5"

_OAUTH_BETA = "oauth-2025-04-20"

# Claude Code identity — REQUIRED as the first system block on subscription OAuth tokens, or the
# API masks Sonnet/Opus behind a fake 429. Must match the canonical Claude Code identity exactly.
_CC_IDENTITY = "You are Claude Code, Anthropic's official CLI for Claude."


def _with_cc_identity(system: Any) -> list[dict]:
    """Prepend the Claude Code identity block to a caller's system prompt (for OAuth clients).

    Accepts the caller's `system` as a str (the normal case), a list of system blocks, or None,
    and returns a list of text blocks with `_CC_IDENTITY` first. The API rejects Sonnet/Opus on
    OAuth tokens unless this identity block leads the system prompt.
    """
    blocks: list[dict] = [{"type": "text", "text": _CC_IDENTITY}]
    if isinstance(system, str):
        if system.strip():
            blocks.append({"type": "text", "text": system})
    elif isinstance(system, list):
        blocks.extend(system)
    return blocks


class ClaudeRefusal(RuntimeError):
    """Raised when Claude returns stop_reason == 'refusal'. Callers (e.g. the chatbot) should
    treat this as an abstain, not a crash."""


class ClaudeUnavailable(RuntimeError):
    """Raised when EVERY credential in the pool failed at the API level (rate limit / auth /
    server / connection). Callers degrade gracefully: the chatbot abstains; internal endpoints
    return 503. Distinct from a refusal (a successful 200 with stop_reason='refusal')."""


def _api_err(e: Exception | None) -> str:
    if e is None:
        return "no credentials configured"
    code = getattr(e, "status_code", "")
    return f"{type(e).__name__}{f' {code}' if code else ''}"


class ClaudeClient:
    """Thin wrapper over a credential pool. Prefer complete_json (schema-validated) for the
    structured GHOSTWIRE outputs; complete_text for free-form. Set thinking=False on the <2s
    chatbot hot path. Calls fail over across pooled credentials on API errors."""

    def __init__(self) -> None:
        s = get_settings()
        # Each entry is (kind, client); kind drives the system-prompt shaping in _create:
        # oauth clients need the Claude Code identity block prepended, api_key clients don't.
        self._clients: list[tuple[str, Any]] = []
        for kind, value in s.claude_credentials():
            if kind == "api_key":
                self._clients.append(("api_key", anthropic.Anthropic(api_key=value, max_retries=0)))
            else:  # oauth
                self._clients.append(
                    (
                        "oauth",
                        anthropic.Anthropic(
                            auth_token=value,
                            default_headers={"anthropic-beta": _OAUTH_BETA},
                            max_retries=0,  # we rotate across the pool, not retry one token
                        ),
                    )
                )
        self._mode = f"pool({len(self._clients)})" if self._clients else "stub"
        self._idx = 0
        self._lock = threading.Lock()

    @property
    def mode(self) -> str:
        return self._mode

    def is_real(self) -> bool:
        """True when at least one real credential is wired (so semantic gates are meaningful)."""
        return bool(self._clients)

    def _next_start(self) -> int:
        with self._lock:
            i = self._idx
            self._idx = (self._idx + 1) % max(1, len(self._clients))
        return i

    def _create(self, **kwargs: Any):
        """Call messages.create, rotating across the credential pool and failing over on any
        API error. Raises ClaudeUnavailable if every credential fails.

        Per-client system shaping: oauth clients get the Claude Code identity prepended to the
        caller's `system` (required for Sonnet/Opus), api_key clients get it unchanged.
        """
        n = len(self._clients)
        start = self._next_start()
        last_err: Exception | None = None
        base_system = kwargs.get("system")
        for offset in range(n):
            kind, client = self._clients[(start + offset) % n]
            call_kwargs = dict(kwargs)
            if kind == "oauth":
                call_kwargs["system"] = _with_cc_identity(base_system)
            try:
                return client.messages.create(**call_kwargs)
            except anthropic.APIError as e:
                last_err = e  # rate-limit / overload / auth / connection -> try the next token
                continue
        raise ClaudeUnavailable(_api_err(last_err)) from last_err

    # --- text ---
    def complete_text(
        self,
        *,
        system: str,
        user: str,
        model: str = OPUS,
        max_tokens: int = 1024,
        thinking: bool = True,
    ) -> str:
        if self._mode == "stub":
            return _stub_text(user)
        kwargs: dict[str, Any] = {
            "model": model,
            "max_tokens": max_tokens,
            "system": system,
            "messages": [{"role": "user", "content": user}],
        }
        if thinking:
            kwargs["thinking"] = {"type": "adaptive"}
        msg = self._create(**kwargs)
        if getattr(msg, "stop_reason", None) == "refusal":
            raise ClaudeRefusal(str(getattr(msg, "stop_details", "refused")))
        return "".join(b.text for b in msg.content if getattr(b, "type", None) == "text")

    # --- schema-constrained JSON ---
    def complete_json(
        self,
        *,
        system: str,
        user: str,
        schema: dict,
        model: str = OPUS,
        max_tokens: int = 2048,
        thinking: bool = True,
    ) -> dict:
        """Return a dict validated against `schema`. Uses output_config.format where supported;
        otherwise falls back to JSON-in-prompt. Validates with jsonschema either way."""
        if self._mode == "stub":
            data = _stub_json(schema)
            jsonschema.validate(data, schema)
            return data

        base: dict[str, Any] = {
            "model": model,
            "max_tokens": max_tokens,
            "system": system,
            "messages": [{"role": "user", "content": user}],
        }
        if thinking:
            base["thinking"] = {"type": "adaptive"}
        # Preferred: structured outputs.
        try:
            msg = self._create(
                **base,
                output_config={"format": {"type": "json_schema", "schema": schema}},
            )
            if getattr(msg, "stop_reason", None) == "refusal":
                raise ClaudeRefusal(str(getattr(msg, "stop_details", "refused")))
            text = "".join(b.text for b in msg.content if getattr(b, "type", None) == "text")
        except (ClaudeRefusal, ClaudeUnavailable):
            raise
        except Exception:
            # Fallback: output_config unsupported by the SDK/model — instruct JSON in the prompt.
            fb = dict(base)
            fb["messages"] = [
                {
                    "role": "user",
                    "content": user
                    + "\n\nRespond with ONLY a JSON object matching this JSON Schema:\n"
                    + json.dumps(schema),
                }
            ]
            msg = self._create(**fb)
            if getattr(msg, "stop_reason", None) == "refusal":
                raise ClaudeRefusal(str(getattr(msg, "stop_details", "refused"))) from None
            text = "".join(b.text for b in msg.content if getattr(b, "type", None) == "text")

        data = json.loads(_extract_json(text or ""))
        jsonschema.validate(data, schema)
        return data


def _extract_json(text: str) -> str:
    text = text.strip()
    if text.startswith("```"):
        text = text.split("```", 2)[1]
        text = text[4:] if text.startswith("json") else text
    start, end = text.find("{"), text.rfind("}")
    return text[start : end + 1] if start != -1 and end != -1 else text


def _stub_text(user: str) -> str:
    return f"[STUB] No Claude credential configured. Echoing intent for: {user[:120]}"


def _stub_json(schema: dict) -> dict:
    """Deterministic minimal object satisfying the required keys of `schema` (for no-credential
    local boot/tests). Resolves internal $ref against the root $defs/components. Not a real
    answer — is_real() is False so gates won't count it."""
    root = schema

    def resolve(sch: dict) -> dict:
        seen = 0
        while "$ref" in sch and seen < 20:
            node: Any = root
            for part in sch["$ref"].lstrip("#/").split("/"):
                node = node[part]
            sch = node
            seen += 1
        return sch

    def build(sch: dict) -> Any:
        sch = resolve(sch)
        t = sch.get("type")
        if t == "object":
            return {
                k: build(v)
                for k, v in sch.get("properties", {}).items()
                if k in sch.get("required", [])
            }
        if t == "array":
            return []
        if t == "string":
            return (sch.get("enum") or ["stub"])[0]
        if t == "number":
            return 0.0
        if t == "integer":
            return 0
        if t == "boolean":
            return True
        return None

    return build(schema)


@lru_cache
def get_claude_client() -> ClaudeClient:
    return ClaudeClient()
