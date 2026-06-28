#!/usr/bin/env python3
"""Validate GHOSTWIRE contract artifacts.

Tier-1 `contract-validate` step (and the Phase-A self-check). Checks:
  1. Every schema under system/contracts/ is valid JSON and (if jsonschema is
     installed) a valid JSON Schema.
  2. If project_state.json exists, it validates against project_state.schema.json.

Graceful: if the `jsonschema` package is absent (e.g. before the app venv exists),
falls back to JSON-parse + minimal structural checks and says so. Exit 0 on pass,
1 on failure. Usage: python3 system/scripts/validate_contracts.py [project_root]
"""
import json
import os
import sys

ROOT = sys.argv[1] if len(sys.argv) > 1 else os.getcwd()
CONTRACTS = os.path.join(ROOT, "system", "contracts")
STATE_SCHEMA = os.path.join(CONTRACTS, "project_state.schema.json")
STATE = os.path.join(ROOT, "project_state.json")

try:
    import jsonschema  # type: ignore
    HAVE_JSONSCHEMA = True
except Exception:
    HAVE_JSONSCHEMA = False

ok = True


def fail(msg: str) -> None:
    global ok
    ok = False
    print(f"  FAIL: {msg}")


def load(path: str):
    with open(path, encoding="utf-8") as fh:
        return json.load(fh)


def find_schemas() -> list[str]:
    out = []
    for base, _dirs, files in os.walk(CONTRACTS):
        for f in files:
            if f.endswith(".json"):
                out.append(os.path.join(base, f))
    return sorted(out)


def main() -> int:
    if not os.path.isdir(CONTRACTS):
        print(f"FAIL: contracts dir not found: {CONTRACTS}")
        return 1

    print(f"jsonschema available: {HAVE_JSONSCHEMA}")
    print("Schemas:")
    for path in find_schemas():
        rel = os.path.relpath(path, ROOT)
        try:
            doc = load(path)
        except Exception as e:
            fail(f"{rel}: invalid JSON ({e})")
            continue
        if HAVE_JSONSCHEMA:
            try:
                cls = jsonschema.validators.validator_for(doc)
                cls.check_schema(doc)
                print(f"  OK (valid schema): {rel}")
            except Exception as e:
                fail(f"{rel}: invalid JSON Schema ({e})")
        else:
            if not isinstance(doc, dict) or "type" not in doc and "$defs" not in doc:
                fail(f"{rel}: missing top-level 'type'")
            else:
                print(f"  OK (json + minimal check): {rel}")

    if os.path.exists(STATE):
        print("project_state.json: present")
        try:
            state = load(STATE)
            schema = load(STATE_SCHEMA)
        except Exception as e:
            fail(f"could not load state/schema ({e})")
            return 0 if ok else 1
        if HAVE_JSONSCHEMA:
            try:
                jsonschema.validate(state, schema)
                print("  OK: project_state.json validates against schema")
            except Exception as e:
                fail(f"project_state.json invalid: {e}")
        else:
            req = schema.get("required", [])
            missing = [k for k in req if k not in state]
            if missing:
                fail(f"project_state.json missing required keys: {missing}")
            else:
                print("  OK (minimal): project_state.json has required top-level keys")
    else:
        print("project_state.json: not present yet (expected before Phase 0).")

    print("RESULT:", "PASS" if ok else "FAIL")
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
