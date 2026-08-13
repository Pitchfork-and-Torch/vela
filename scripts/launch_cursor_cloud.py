"""Launch Cursor Cloud Agents for VELA language gaps.

Reads the user API key from Desktop\\cursorapiforyou.txt (never prints it).
Does not schedule Windows tasks. One-shot POST /v1/agents.
"""
from __future__ import annotations

import json
import re
import sys
import urllib.error
import urllib.request
from pathlib import Path

API = "https://api.cursor.com/v1"
REPO = "https://github.com/Pitchfork-and-Torch/vela"
KEY_FILE = Path.home() / "Desktop" / "cursorapiforyou.txt"
OUT = Path(__file__).resolve().parents[1] / "lab" / "cursor-agents.json"

RAILS = """
MISSION (docs/MISSION.md): VELA builds onto LeoAware. It does not compete with it.
Observe-only compose matching LeoAware is a no-regress rail, not a failed rival.

HARD RAILS:
- Do not enable closed-write operators: HorizonChase, TrimFill, TrimReclaim,
  QuietReach, QuietShield, SoftFlicker, TrimHold.
- Do not fork Detect / SoftReprobe.
- Do not change packet-path pace/cwnd policy in vela/kernel.py.
- Do not claim dish Mbps. Dual-gate numbers only from eval JSON.
- Do not mix OPE-fair v3.7 figures with coupled-RNG LeoAware v3.4-p95.
- Keep tests green: python -m unittest discover -s tests -q
- ASCII punctuation only in committed files (no em dashes, no en dashes).
- Open a PR. Do not merge. Do not force-push main.
"""

AGENTS = [
    {
        "name": "VELA JON-11 Interval n>=2",
        "prompt": f"""You are a language engineer on private repo Pitchfork-and-Torch/vela.

Task: Linear JON-11 / GitHub issue #1 / backlog id interval-n2.

LANGUAGE.md uncertainty law: an Interval used as a point (bw in arithmetic)
is implicitly bw.mid and REQUIRES bw.n >= 2. A single sample is not bandwidth.

Today the checker only warns when HorizonChase/QuietReach lack IntervalBw.
Implement a real type error when an Interval-typed name is used as a scalar
in arithmetic or assign without an n>=2 guard.

Implementation sketch:
1. In vela/checker.py walk assign/let/chase/cut expressions.
2. If a name is declared Interval and is used as a point (bare name, not
   .lo/.mid/.hi/.n/.e), emit a CheckResult error unless the same block
   already proved n>=2 (for example `when bw.n >= 2` or an explicit
   `if bw.n >= 2` / `require n>=2`).
3. Attribute access bw.mid / bw.lo / bw.hi still requires the n>=2 proof
   when used as a pacing/cwnd number. Reading bw.n itself is always ok.
4. Add tests in tests/test_parser.py (or tests/test_interval.py):
   - Interval used as point without n>=2 => check().ok is False
   - Interval.mid under `when bw.n >= 2` => ok
   - existing examples (horizon.vela, reach.vela, luff.vela) still check ok
     (they already have IntervalBw; do not break them)
5. One sentence in docs/LANGUAGE.md under the uncertainty law: now enforced.

{RAILS}

Done when unittest is green and the PR description names the new error string.
""",
    },
    {
        "name": "VELA JON-12 compose cuts/growth",
        "prompt": f"""You are a language engineer on private repo Pitchfork-and-Torch/vela.

Task: Linear JON-12 / GitHub issue #2 / backlog id compose-cuts.

LANGUAGE.md: two hard cuts on the same event are a compile error unless the
author writes `compose cuts = min`. Two raisers of cwnd must pick
`compose growth = min | max | sum`.

Today vela/parser.py _compose_list is IDENT + IDENT only. The checker error
string mentions compose cuts = min but the syntax does not parse.

Implement:
1. Parse after the mechanism list, optional:
     compose Detect + SoftReprobe
     compose cuts = min
     compose growth = min
   Allow the clauses on their own lines inside the controller, or as
   trailing clauses after the compose list. Use existing EQ_SIGN token.
   Allowed cuts values: min. Allowed growth values: min | max | sum.
2. Store on ast.Controller: cuts_compose: str | None, growth_compose: str | None.
3. Checker: two hard epoch cuts is still an error UNLESS cuts_compose == "min".
   Two cwnd raisers (any pair among OCE, HorizonChase, TrimFill, QuietReach,
   TrimReclaim) is an error UNLESS growth_compose is set.
4. Tests:
   - parse + check a snippet with two hard epoch cuts and compose cuts = min => ok
   - same without the clause => error
   - parse compose growth = max
   - existing examples still parse (no new required clauses)
5. Update docs/LANGUAGE.md composition section: syntax now exists.

Do not implement a runtime min-of-two-soft-cuts kernel merge. Check-time only.

{RAILS}

Done when unittest is green and the PR shows the new AST fields.
""",
    },
    {
        "name": "VELA JON-13 harness INCOMPLETE",
        "prompt": f"""You are a language engineer on private repo Pitchfork-and-Torch/vela.

Task: Linear JON-13 / GitHub issue #3 / backlog id incomplete-verdict.

LANGUAGE.md: vela eval JSON verdict is ACCEPT / FAIL / INCOMPLETE.
A researcher cannot forget terrestrial without INCOMPLETE.

Today vela/eval_harness.py _summarize sets top-level verdict ACCEPT if all
asserts ok else FAIL. Missing terrestrial is an assert with ok=False and
note=INCOMPLETE, so the top-level verdict is FAIL. That hides the honesty
state LANGUAGE.md promised.

Implement:
1. Top-level verdict:
   - INCOMPLETE if any assert has note INCOMPLETE, or terrestrial_floor is
     missing, or n_seeds < contract minimum (keep power=low when n<8)
   - FAIL if a present assert is false (dual-gate vs BBR, vs LeoAware
     no-regress, terrestrial floor when the row exists and is below 77@40)
   - ACCEPT only when every required assert is present and ok
2. INCOMPLETE is not ACCEPT. Do not let a missing terrestrial look like FAIL
   for a dual-gate miss. Missing data is incomplete; a measured miss is fail.
3. Tests: add tests/test_eval_verdict.py that calls the summarizer with
   fixture tables (no live leo-aware-transport run required). Cover ACCEPT,
   FAIL (terrestrial present but below floor), INCOMPLETE (no terrestrial row).
4. One sentence in docs/LANGUAGE.md contracts section: top-level INCOMPLETE
   is now emitted.

Do not run house-gate sims. Do not enable write operators.

{RAILS}

Done when unittest is green and a fixture proves verdict == INCOMPLETE.
""",
    },
]


def load_key() -> str:
    raw = KEY_FILE.read_text(encoding="utf-8")
    for line in raw.splitlines():
        s = line.strip()
        if s.startswith("crsr_"):
            return s
    s = raw.strip()
    if s.startswith("crsr_"):
        return s
    raise SystemExit("no crsr_ key in Desktop cursorapiforyou.txt")


def req(method: str, path: str, key: str, body: dict | None = None) -> dict:
    data = None
    headers = {"Accept": "application/json"}
    if body is not None:
        data = json.dumps(body).encode("utf-8")
        headers["Content-Type"] = "application/json"
    url = API + path
    # Basic key:
    import base64

    token = base64.b64encode(f"{key}:".encode("ascii")).decode("ascii")
    headers["Authorization"] = f"Basic {token}"
    r = urllib.request.Request(url, data=data, headers=headers, method=method)
    try:
        with urllib.request.urlopen(r, timeout=120) as resp:
            raw = resp.read().decode("utf-8")
            return json.loads(raw) if raw else {}
    except urllib.error.HTTPError as e:
        err = e.read().decode("utf-8", errors="replace")
        raise SystemExit(f"{method} {path} -> {e.code} {err[:2000]}")


def main() -> int:
    key = load_key()
    if not re.fullmatch(r"crsr_[0-9a-fA-F]{64}", key):
        print("WARN key shape unexpected, still trying", file=sys.stderr)
    me = req("GET", "/me", key)
    print(f"me key={me.get('apiKeyName')} userId={me.get('userId')}")

    launched = []
    for spec in AGENTS:
        body = {
            "prompt": {"text": spec["prompt"]},
            "name": spec["name"],
            "model": {
                "id": "grok-4.6",
                "params": [
                    {"id": "effort", "value": "high"},
                    {"id": "fast", "value": "true"},
                ],
            },
            "repos": [{"url": REPO, "startingRef": "main"}],
            "autoCreatePR": True,
            "skipReviewerRequest": True,
            "mode": "agent",
        }
        print(f"POST agent {spec['name']} ...")
        out = req("POST", "/agents", key, body)
        agent = out.get("agent") or {}
        run = out.get("run") or {}
        rec = {
            "name": spec["name"],
            "id": agent.get("id"),
            "url": agent.get("url"),
            "status": agent.get("status"),
            "runId": run.get("id"),
            "runStatus": run.get("status"),
        }
        print(json.dumps(rec, indent=2))
        launched.append(rec)

    OUT.write_text(json.dumps({"agents": launched}, indent=2) + "\n", encoding="utf-8")
    print(f"wrote {OUT}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
