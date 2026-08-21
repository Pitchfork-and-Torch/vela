"""One tick of the space-internet cook loop. Isolated evals. No closed writes."""
from __future__ import annotations

import argparse
import json
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
LAB = ROOT / "lab"
BACKLOG = LAB / "BACKLOG.json"
STATE = LAB / "STATE.md"
JOURNAL = LAB / "journal.jsonl"
PUBLIC = LAB / "PUBLIC_PROGRESS.json"
STOP = LAB / "STOP"
SANITIZER = Path.home() / "orbitstack" / "scripts" / "publish_progress.py"
ORBIT_PROGRESS = Path.home() / "orbitstack" / "public" / "progress.json"


def _now() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _load_backlog() -> dict:
    return json.loads(BACKLOG.read_text(encoding="utf-8"))


def _save_backlog(data: dict) -> None:
    BACKLOG.write_text(json.dumps(data, indent=2) + "\n", encoding="utf-8", newline="\n")


def _append_journal(row: dict) -> None:
    with JOURNAL.open("a", encoding="utf-8", newline="\n") as f:
        f.write(json.dumps(row, separators=(",", ":")) + "\n")


def _write_state(*, last: str, nxt: str, status: str, extra: str = "") -> None:
    STATE.write_text(
        "\n".join(
            [
                "# Loop state",
                "",
                f"status: {status}",
                f"updated: {_now()}",
                "engine: LeoAware v3.4-p95 on this machine (73.57 / 138.37 vs BBR 70.88 / 138.83)",
                "vela: 0.4 Ingress, observe-only Reach, no-oracle",
                f"last_job: {last}",
                f"next_job: {nxt}",
                f"stop: {'yes' if STOP.exists() else 'no'}",
                extra,
                "",
            ]
        ),
        encoding="utf-8",
        newline="\n",
    )


def _public_log(note: str, verdict: str) -> None:
    data = json.loads(PUBLIC.read_text(encoding="utf-8"))
    data["updated"] = _now()[:10]
    data.setdefault("log", []).append(
        {"date": data["updated"], "note": note, "verdict": verdict}
    )
    PUBLIC.write_text(json.dumps(data, indent=2) + "\n", encoding="utf-8", newline="\n")


def _next_item(data: dict) -> dict | None:
    for it in data["items"]:
        if it.get("status") == "pending":
            return it
    return None


def _run_eval_passthrough() -> dict:
    import sys

    sys.path.insert(0, str(ROOT))
    from vela.eval_harness import passthrough_ok, run_one_isolated, write_passthrough_result
    from vela.ir import VelaConfig, program_to_config
    from vela.parser import parse

    src = (ROOT / "examples" / "reach.vela").read_text(encoding="utf-8")
    cfg = program_to_config(parse(src, "reach.vela"))
    leo = run_one_isolated("LeoAware", "leo_fast_ho", 7, 45.0, VelaConfig(name="LeoAware"))
    reach = run_one_isolated("Reach", "leo_fast_ho", 7, 45.0, cfg)
    ok = passthrough_ok(leo, reach)
    write_passthrough_result(leo, reach, ok=ok, ran=_now())
    return {
        "ok": ok,
        "leo": leo,
        "reach": reach,
        "note": (
            f"passthrough seed7 45s Leo {leo['goodput_mbps']:.2f}/{leo['p95_rtt_ms']:.1f} "
            f"Reach {reach['goodput_mbps']:.2f}/{reach['p95_rtt_ms']:.1f}"
        ),
    }


def tick() -> int:
    if STOP.exists():
        _write_state(last="none", nxt="none", status="stopped", extra="STOP file present.")
        print("STOP present. Exit.")
        return 0
    data = _load_backlog()
    item = _next_item(data)
    if item is None:
        _write_state(last="none", nxt="none", status="idle", extra="Backlog empty.")
        print("Backlog empty.")
        return 0

    print(f"job {item['id']} kind={item['kind']}", flush=True)
    result = {"ok": False, "note": "unrun"}
    if item["kind"] == "eval" and item["id"] == "confirm-passthrough":
        result = _run_eval_passthrough()
        item["status"] = "done" if result["ok"] else "fail"
    elif item["kind"] == "language":
        result = {
            "ok": True,
            "note": f"queued for Language agent: {item['note']}",
        }
        item["status"] = "needs_agent"
    else:
        result = {"ok": False, "note": f"unknown job {item['id']}"}
        item["status"] = "fail"

    _save_backlog(data)
    nxt = _next_item(data)
    _append_journal(
        {
            "t": _now(),
            "id": item["id"],
            "status": item["status"],
            "note": result.get("note"),
            "detail": {k: result[k] for k in result if k not in ("ok", "note")},
        }
    )
    if item.get("public") and item["status"] in ("done", "needs_agent"):
        _public_log(result["note"], item["status"])
    _write_state(
        last=item["id"],
        nxt=(nxt["id"] if nxt else "none"),
        status="ok" if result["ok"] else "fail",
        extra=result.get("note", ""),
    )
    print(result.get("note"), flush=True)
    return 0 if result["ok"] else 3


def publish(
    *,
    src: Path | None = None,
    dest: Path | None = None,
    sanitizer: Path | None = None,
    dry_run: bool = False,
) -> int:
    """Merge lab PUBLIC_PROGRESS through the orbitstack sanitizer.

    Never naive-copy the lab file onto public/progress.json. That clobbers
    the locked Current (v3.9 Crest 82.07 / 76.26) with coupled-era notes.
    """
    src = src or PUBLIC
    dest = dest or ORBIT_PROGRESS
    sanitizer = sanitizer or SANITIZER
    if not sanitizer.is_file():
        print(f"FAIL publish: missing sanitizer {sanitizer}")
        return 2
    if not src.is_file():
        print(f"FAIL publish: missing lab progress {src}")
        return 2
    cmd = [sys.executable, str(sanitizer), "--src", str(src), "--dest", str(dest)]
    if dry_run:
        cmd.append("--dry-run")
    proc = subprocess.run(cmd, check=False)
    if proc.returncode != 0:
        print(f"FAIL publish: sanitizer exit {proc.returncode}")
    return int(proc.returncode)


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--once", action="store_true")
    ap.add_argument("--publish", action="store_true")
    ap.add_argument(
        "--dry-run",
        action="store_true",
        help="With --publish, run the sanitizer without writing dest.",
    )
    args = ap.parse_args(argv)
    LAB.mkdir(parents=True, exist_ok=True)
    if not JOURNAL.exists():
        JOURNAL.write_text("", encoding="utf-8")
    if args.publish:
        code = publish(dry_run=args.dry_run)
        if code != 0:
            return code
        if not args.once:
            return 0
    return tick()


if __name__ == "__main__":
    raise SystemExit(main())
