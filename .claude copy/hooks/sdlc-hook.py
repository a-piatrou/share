#!/usr/bin/env python3
"""GHOSTWIRE SDLC hook dispatcher.

Wired in .claude/settings.json for SessionStart, SubagentStop, TaskCompleted, Stop.
- SessionStart : reload skills + inject a compact build-state context line.
- SubagentStop / TaskCompleted : observability log + a PRECISE, non-looping gate that
  blocks completion only when a builder marked its module status=done while verify_status
  is not green (the exact "claimed done without a green verify" anti-pattern). The lead
  re-verifies the merged tree regardless.
- Stop : append a turn-end marker to the build-event trail.

Reads the hook payload as JSON on stdin, emits decision JSON on stdout, exits 0.
Fail-open: any error => pass (never block the build on a hook bug)."""
import json
import os
import sys
from datetime import datetime, timezone

PROJECT = os.environ.get("CLAUDE_PROJECT_DIR") or os.getcwd()
STATE = os.path.join(PROJECT, "project_state.json")
LOG = os.path.join(PROJECT, "system", "sdlc", "build-events.log")

# agent_type (subagent name) -> module id in project_state.json
AGENT_TO_MODULE = {
    "knowledge-core-builder": "knowledge_core",
    "chatbot-builder": "chatbot",
    "feedback-builder": "feedback",
    "team-assembler-builder": "team_assembler",
    "frontend-builder": "frontend",
}
GREEN = {"tier1_green", "tier2_green"}


def log(line: str) -> None:
    try:
        os.makedirs(os.path.dirname(LOG), exist_ok=True)
        ts = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
        with open(LOG, "a", encoding="utf-8") as fh:
            fh.write(f"{ts} {line}\n")
    except Exception:
        pass


def load_state():
    try:
        with open(STATE, encoding="utf-8") as fh:
            return json.load(fh)
    except Exception:
        return None


def emit(obj: dict) -> None:
    sys.stdout.write(json.dumps(obj))
    sys.exit(0)


def main() -> None:
    try:
        raw = sys.stdin.read()
        data = json.loads(raw) if raw.strip() else {}
    except Exception:
        sys.exit(0)  # malformed input => pass

    event = data.get("hook_event_name", "")

    if event == "SessionStart":
        st = load_state()
        if st:
            ctx = (
                f"GHOSTWIRE build active. contract_version={st.get('contract_version')}. "
                "project_state.json is the source of truth; PROGRESS.md tracks stages."
            )
        else:
            ctx = "GHOSTWIRE SDLC system loaded. No project_state.json yet (pre-Phase-0)."
        emit({"hookSpecificOutput": {
            "hookEventName": "SessionStart",
            "reloadSkills": True,
            "additionalContext": ctx,
        }})

    if event in ("SubagentStop", "TaskCompleted"):
        agent = data.get("agent_type", "")
        module = AGENT_TO_MODULE.get(agent)
        log(f"{event} agent={agent or '?'} task={data.get('task_name','')}")
        if module:
            st = load_state()
            if st:
                for m in st.get("modules", []):
                    if m.get("id") == module and m.get("status") == "done" \
                            and m.get("verify_status") not in GREEN:
                        log(f"GATE BLOCK {module}: status=done but verify_status="
                            f"{m.get('verify_status')}")
                        emit({"decision": "block", "reason": (
                            f"Module '{module}' is marked status=done but verify_status="
                            f"{m.get('verify_status')!r}. Run `make verify` to green (tier-1: "
                            "compile/type/lint/contract-validate/boot/smoke) and update "
                            "verify_status in project_state.json before finishing.")})
        sys.exit(0)  # pass

    if event == "Stop":
        log("Stop (turn ended)")
        sys.exit(0)

    sys.exit(0)


if __name__ == "__main__":
    main()
