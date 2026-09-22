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
RESULTS = ROOT / "results"
BACKLOG = LAB / "BACKLOG.json"
STATE = LAB / "STATE.md"
JOURNAL = LAB / "journal.jsonl"
PUBLIC = LAB / "PUBLIC_PROGRESS.json"
STOP = LAB / "STOP"
LOOP_LOG = RESULTS / "loop_ticks.jsonl"
LOOP_LAST = RESULTS / "loop_last.json"
SANITIZER = Path.home() / "orbitstack" / "scripts" / "publish_progress.py"
ORBIT_PROGRESS = Path.home() / "orbitstack" / "public" / "progress.json"

# Actuator-known kinds. Kernel / closed-write enablements are never auto-run.
KNOWN_KINDS = frozenset({"eval", "language"})
KNOWN_EVAL_IDS = frozenset({"confirm-passthrough", "passthrough-seed7-reconfirm"})


def _now() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _load_backlog() -> dict:
    return json.loads(BACKLOG.read_text(encoding="utf-8"))


def _save_backlog(data: dict) -> None:
    BACKLOG.write_text(json.dumps(data, indent=2) + "\n", encoding="utf-8", newline="\n")


def _append_journal(row: dict) -> None:
    with JOURNAL.open("a", encoding="utf-8", newline="\n") as f:
        f.write(json.dumps(row, separators=(",", ":")) + "\n")


def _write_results(row: dict) -> None:
    """Always log ticks under results/ (gitignored). Never a public publish path."""
    RESULTS.mkdir(parents=True, exist_ok=True)
    payload = dict(row)
    payload.setdefault("t", _now())
    LOOP_LAST.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8", newline="\n")
    with LOOP_LOG.open("a", encoding="utf-8", newline="\n") as f:
        f.write(json.dumps(payload, separators=(",", ":")) + "\n")


def _write_state(*, last: str, nxt: str, status: str, extra: str = "") -> None:
    STATE.write_text(
        "\n".join(
            [
                "# Loop state",
                "",
                f"status: {status}",
                f"updated: {_now()}",
                "engine: LeoAware v3.4-p95 on this machine (73.57 / 138.37 vs BBR 70.88 / 138.83)",
                "vela: 0.4.3 affine + WriteCap linear + hybrid automata, observe-only Reach",
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
    """Lab-local progress only. Public sites must use publish() + sanitizer."""
    data = json.loads(PUBLIC.read_text(encoding="utf-8"))
    data["updated"] = _now()[:10]
    data.setdefault("log", []).append(
        {"date": data["updated"], "note": note, "verdict": verdict}
    )
    PUBLIC.write_text(json.dumps(data, indent=2) + "\n", encoding="utf-8", newline="\n")


def _is_closed_write_enable(item: dict) -> bool:
    if item.get("enable_closed_write") is True:
        return True
    blob = " ".join(str(item.get(k, "")) for k in ("id", "note", "kind")).lower()
    needles = (
        "enable closed-write",
        "enable closed write",
        "packet-path enable",
        "merge review compose",
    )
    return any(n in blob for n in needles)


def _next_item(data: dict) -> dict | None:
    """Next safe, pending, actuator-known item. Skips unsafe / closed-write enables."""
    for it in data["items"]:
        if it.get("status") != "pending":
            continue
        if it.get("safe") is not True:
            continue
        if it.get("kind") not in KNOWN_KINDS:
            continue
        if _is_closed_write_enable(it):
            continue
        return it
    return None


def _pending_safe_count(data: dict) -> int:
    n = 0
    for it in data["items"]:
        if (
            it.get("status") == "pending"
            and it.get("safe") is True
            and it.get("kind") in KNOWN_KINDS
            and not _is_closed_write_enable(it)
        ):
            n += 1
    return n


def _run_eval_passthrough() -> dict:
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


def tick(*, dry_run: bool = False) -> int:
    if STOP.exists():
        note = "STOP file present."
        _write_results({"event": "stop", "dry_run": dry_run, "note": note})
        if not dry_run:
            _write_state(last="none", nxt="none", status="stopped", extra=note)
        print("STOP present. Exit.")
        return 0
    data = _load_backlog()
    item = _next_item(data)
    if item is None:
        note = (
            f"Backlog empty of safe pending language/eval items "
            f"(scanned {len(data.get('items', []))})."
        )
        _write_results({"event": "idle", "dry_run": dry_run, "note": note})
        if not dry_run:
            _write_state(last="none", nxt="none", status="idle", extra=note)
        print(note)
        return 0

    print(
        f"job {item['id']} kind={item['kind']} safe={item.get('safe')} "
        f"dry_run={dry_run} pending_safe={_pending_safe_count(data)}",
        flush=True,
    )

    if dry_run:
        preview = {
            "event": "dry_run",
            "dry_run": True,
            "id": item["id"],
            "kind": item["kind"],
            "safe": item.get("safe"),
            "public": item.get("public"),
            "note": item.get("note"),
            "would_status": (
                "done_or_fail_via_eval"
                if item["kind"] == "eval" and item["id"] in KNOWN_EVAL_IDS
                else "needs_agent"
            ),
        }
        _write_results(preview)
        print(f"dry-run: would act on {item['id']}: {item.get('note')}", flush=True)
        print("dry-run: no backlog/STATE/PUBLIC_PROGRESS/journal mutation.", flush=True)
        return 0

    result: dict = {"ok": False, "note": "unrun"}
    if item["kind"] == "eval" and item["id"] in KNOWN_EVAL_IDS:
        result = _run_eval_passthrough()
        item["status"] = "done" if result["ok"] else "fail"
    elif item["kind"] == "language":
        result = {
            "ok": True,
            "note": f"queued for Language agent: {item['note']}",
        }
        item["status"] = "needs_agent"
    elif item["kind"] == "eval":
        # Unknown eval id: queue for Measurer; do not invent a runner.
        result = {
            "ok": True,
            "note": f"queued for Measurer agent: {item['note']}",
        }
        item["status"] = "needs_agent"
    else:
        result = {"ok": False, "note": f"unknown job {item['id']}"}
        item["status"] = "fail"

    _save_backlog(data)
    nxt = _next_item(data)
    journal_row = {
        "t": _now(),
        "id": item["id"],
        "status": item["status"],
        "note": result.get("note"),
        "detail": {k: result[k] for k in result if k not in ("ok", "note")},
    }
    _append_journal(journal_row)
    _write_results(
        {
            "event": "tick",
            "dry_run": False,
            "id": item["id"],
            "kind": item["kind"],
            "status": item["status"],
            "ok": result.get("ok"),
            "note": result.get("note"),
            "next": (nxt["id"] if nxt else "none"),
        }
    )
    # Lab-local only. Never a substitute for publish() + sanitizer.
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
        _write_results(
            {
                "event": "publish",
                "ok": False,
                "dry_run": dry_run,
                "note": f"missing sanitizer {sanitizer}",
            }
        )
        return 2
    if not src.is_file():
        print(f"FAIL publish: missing lab progress {src}")
        _write_results(
            {
                "event": "publish",
                "ok": False,
                "dry_run": dry_run,
                "note": f"missing lab progress {src}",
            }
        )
        return 2
    cmd = [sys.executable, str(sanitizer), "--src", str(src), "--dest", str(dest)]
    if dry_run:
        cmd.append("--dry-run")
    proc = subprocess.run(cmd, check=False)
    if proc.returncode != 0:
        print(f"FAIL publish: sanitizer exit {proc.returncode}")
    _write_results(
        {
            "event": "publish",
            "ok": proc.returncode == 0,
            "dry_run": dry_run,
            "sanitizer": str(sanitizer),
            "src": str(src),
            "dest": str(dest),
            "note": "sanitizer invoked; never naive-copy",
        }
    )
    return int(proc.returncode)


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(
        description=(
            "Space-internet cook loop actuator. "
            "Requires --once to tick. --publish always uses the sanitizer."
        )
    )
    ap.add_argument(
        "--once",
        action="store_true",
        help="Run one backlog tick (safe pending language/eval only).",
    )
    ap.add_argument(
        "--publish",
        action="store_true",
        help="Publish via orbitstack sanitizer. Never naive-copies lab JSON.",
    )
    ap.add_argument(
        "--dry-run",
        action="store_true",
        help=(
            "With --once: preview next job; no lab mutation. "
            "With --publish: run sanitizer without writing dest."
        ),
    )
    args = ap.parse_args(argv)
    LAB.mkdir(parents=True, exist_ok=True)
    RESULTS.mkdir(parents=True, exist_ok=True)
    if not JOURNAL.exists():
        JOURNAL.write_text("", encoding="utf-8")
    if not args.once and not args.publish:
        ap.print_help()
        print("\nNothing to do: pass --once and/or --publish.", flush=True)
        return 2
    if args.publish:
        code = publish(dry_run=args.dry_run)
        if code != 0:
            return code
        if not args.once:
            return 0
    if args.once:
        return tick(dry_run=args.dry_run)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
