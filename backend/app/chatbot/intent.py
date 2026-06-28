"""Intent detection for the public chatbot (REQ-006).

Maps a query to one of ``client | candidate | unknown`` and then to the frozen retrieval
``DomainFilter`` from ``INTENT_DOMAINS`` (all within the public PII-free set).

Detection is intentionally cheap to protect the <2s budget (REQ-004):
1. A fast keyword heuristic that decides most queries with no network call.
2. Only when the heuristic is ambiguous AND a real Claude credential is wired do we fall back
   to a single HAIKU ``complete_text`` classify (no thinking). In stub mode we never call Claude
   for intent — the heuristic (or "unknown") is used so boot/tests stay offline and fast.
"""

from __future__ import annotations

from app.chatbot.prompts import INTENT_SYSTEM_PROMPT
from app.contracts import INTENT_DOMAINS, DomainFilter
from app.llm import HAIKU, ClaudeRefusal, get_claude_client

Intent = str  # one of "client" | "candidate" | "unknown"

_VALID: frozenset[str] = frozenset({"client", "candidate", "unknown"})

# Lightweight lexical signals. Deliberately small; the LLM is the tiebreaker when wired.
_CANDIDATE_HINTS = (
    "job",
    "jobs",
    "career",
    "careers",
    "hiring",
    "hire me",
    "vacancy",
    "vacancies",
    "opening",
    "openings",
    "position",
    "apply",
    "application",
    "resume",
    "cv",
    "interview",
    "salary",
    "work here",
    "working here",
    "join the team",
    "join your",
    "recruit",
    "internship",
    "intern ",
)
_CLIENT_HINTS = (
    "service",
    "services",
    "case study",
    "case studies",
    "portfolio",
    "client",
    "pricing",
    "price",
    "quote",
    "project",
    "engagement",
    "consult",
    "company",
    "about you",
    "what do you do",
    "your work",
    "past work",
    "expertise",
    "capabilit",
    "partner",
    "contract us",
    "hire your",
)


def _heuristic(query: str) -> Intent | None:
    """Return a confident intent, or None when ambiguous (no/both signals)."""
    q = query.lower()
    candidate = any(h in q for h in _CANDIDATE_HINTS)
    client = any(h in q for h in _CLIENT_HINTS)
    if candidate and not client:
        return "candidate"
    if client and not candidate:
        return "client"
    return None  # ambiguous -> let the LLM (if real) decide


def _classify_llm(query: str) -> Intent:
    """Single cheap HAIKU classify. Falls back to 'unknown' on refusal/garbage."""
    client = get_claude_client()
    try:
        raw = client.complete_text(
            system=INTENT_SYSTEM_PROMPT,
            user=query,
            model=HAIKU,
            max_tokens=8,
            thinking=False,
        )
    except ClaudeRefusal:
        return "unknown"
    token = raw.strip().lower().strip(".\"'` ")
    return token if token in _VALID else "unknown"


def detect_intent(query: str) -> Intent:
    """Detect audience intent. Heuristic first; HAIKU tiebreak only when a real credential is
    wired (stub mode never calls Claude here, keeping boot offline)."""
    guess = _heuristic(query)
    if guess is not None:
        return guess
    if get_claude_client().is_real():
        return _classify_llm(query)
    return "unknown"


def domain_filter_for(intent: Intent) -> DomainFilter:
    """Map a detected intent to its frozen public retrieval domains (INTENT_DOMAINS)."""
    domains = INTENT_DOMAINS.get(intent, INTENT_DOMAINS["unknown"])
    return DomainFilter(domains=domains)
