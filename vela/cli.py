"""VELA command line."""
from __future__ import annotations

import argparse
import json
from pathlib import Path

from vela import __version__
from vela.checker import check
from vela.compile import compile_file, compile_source
from vela.parser import ParseError, parse
from vela.types import POWER_OK_MIN_SEEDS, power_cli_line


class InputError(Exception):
    """An input file could not be read or decoded. Exit 2, no traceback."""


def _read_text(path: str | Path, what: str) -> str:
    try:
        return Path(path).read_text(encoding="utf-8")
    except OSError as e:
        raise InputError(f"cannot read {what} {path}: {e.strerror or e}") from e
    except UnicodeDecodeError as e:
        raise InputError(f"{what} {path} is not UTF-8 text: {e.reason}") from e


def _read_json(path: str | Path, what: str):
    text = _read_text(path, what)
    try:
        return json.loads(text)
    except json.JSONDecodeError as e:
        raise InputError(f"{what} {path} is not valid JSON: {e.msg} (line {e.lineno})") from e


def main(argv: list[str] | None = None) -> int:
    try:
        return _main(argv)
    except InputError as e:
        print(f"error: {e}")
        return 2


def _main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(prog="vela", description="VELA compiler and eval")
    ap.add_argument("--version", action="version", version=f"VELA {__version__}")
    sub = ap.add_subparsers(dest="cmd", required=True)

    p_chk = sub.add_parser("check", help="parse + type-check")
    p_chk.add_argument("file")

    p_cmp = sub.add_parser("compile", help="lower to Python kernel config")
    p_cmp.add_argument("file")
    p_cmp.add_argument("-o", "--out", default=None)
    p_cmp.add_argument("--view", default=None)

    p_ev = sub.add_parser(
        "eval",
        help="run the contract on leo-aware-transport (JSON is the claim)",
    )
    p_ev.add_argument("file")
    p_ev.add_argument("--seeds", default=None)
    p_ev.add_argument(
        "--fast",
        action="store_true",
        help="2 seeds, 45s, gate=fast. Not the house gate. Do not mix --seeds/--duration.",
    )
    p_ev.add_argument("--duration", type=float, default=None)
    p_ev.add_argument("--oce", action="store_true")
    p_ev.add_argument(
        "--tag",
        default=None,
        help="result tag (default: controller name)",
    )
    p_ev.add_argument("--view", default=None)

    p_rs = sub.add_parser("emit-rust", help="emit Rust IR sketch")
    p_rs.add_argument("file")
    p_rs.add_argument("-o", "--out", default=None)

    p_dig = sub.add_parser("digest", help="content-address a program or the stdlib")
    p_dig.add_argument("file", nargs="?")
    p_dig.add_argument("--stdlib", action="store_true")

    p_rcpt = sub.add_parser("receipt", help="verify an eval receipt")
    p_rcpt.add_argument("file")
    p_rcpt.add_argument("--source", default=None)
    p_rcpt.add_argument(
        "--eval",
        default=None,
        dest="eval_json",
        help="eval JSON whose rows the receipt commits",
    )

    sub.add_parser("mech", help="list stdlib mechanisms with digests")

    args = ap.parse_args(argv)

    if args.cmd == "mech":
        from vela.digest import stdlib_catalog

        cat = stdlib_catalog()
        for name, digest in cat.items():
            print(f"{digest[:16]}  {name}")
        print(f"{len(cat)} mechanisms")
        return 0

    if args.cmd == "digest" and args.stdlib:
        from vela.digest import stdlib_catalog

        print(json.dumps(stdlib_catalog(), indent=2))
        return 0

    if args.cmd == "receipt":
        from vela.receipt import verify_receipt

        rec = _read_json(args.file, "receipt")
        src = None
        if args.source:
            src = _read_text(args.source, "source")
        summary = None
        if args.eval_json:
            summary = _read_json(args.eval_json, "eval JSON")
        errs = verify_receipt(rec, source=src, summary=summary)
        if errs:
            for e in errs:
                print(f"error: {e}")
            return 1
        bound = "bound" if summary is not None else "unbound"
        print(
            f"ok  receipt={rec.get('receipt_digest', '')[:16]}  "
            f"verdict={rec.get('verdict')}  gate={rec.get('gate') or '-'}  "
            f"rows={bound}"
        )
        # power=low for n<8 on the receipt CLI (align check + harness).
        n_seeds = rec.get("n_seeds")
        if n_seeds is None and isinstance(summary, dict):
            n_seeds = summary.get("n_seeds")
        if n_seeds is not None:
            print(f"    {power_cli_line(int(n_seeds))}")
        elif rec.get("power") == "low":
            print(f"    power=low  (n<{POWER_OK_MIN_SEEDS}  not journal)")
        elif rec.get("power") == "ok":
            print(f"    power=ok  (n>={POWER_OK_MIN_SEEDS})")
        if summary is None:
            print("    pass --eval to bind seed rows (a swapped number fails then)")
        return 0

    if not getattr(args, "file", None):
        print("file required")
        return 2

    path = Path(args.file)
    src = _read_text(path, "program")
    try:
        prog = parse(src, str(path))
    except ParseError as e:
        print(f"parse error: {e}")
        return 2

    if args.cmd == "digest":
        from vela.digest import compose_digest, source_digest

        c = prog.controllers[0]
        print(f"source   {source_digest(src)}")
        print(f"compose  {compose_digest(c.compose)}")
        print(f"controller {c.name}")
        return 0

    if args.cmd == "check":
        res = check(prog)
        for w in res.warnings:
            print(f"warning: {w}")
        if not res.ok:
            for e in res.errors:
                print(f"error: {e}")
            return 1
        c = prog.controllers[0]
        print(f"ok  controller={c.name}  compose={' + '.join(c.compose)}")
        if res.observe_only:
            print("    observe-only  (no closed-write)")
        else:
            print(f"    posture={c.posture}")
        if res.hint_fail_closed:
            print("    hint=fail-closed  (missing is None, not a hop oracle)")
        if res.typed_reconfig:
            print("    reconfig=RttHop|Flicker  (house cut 0.58)")
        if res.typed_loss:
            print("    loss=Mobility|Congestive|Unknown  (hold / cut / delay_ratio)")
        if res.passthrough:
            print("    passthrough  (LeoAware wrap; no cruise write)")
        if res.no_oracle:
            print("    no-oracle  (endpoint cannot see next_capacity)")
        if res.affine:
            print("    affine  (Sample @ e is use-once; e+1 is prior)")
        if res.hybrid:
            print("    hybrid  (on = jump; when/every = flow)")
        if res.writecap == "linear":
            print("    writecap=linear  (split/borrow; no ambient write)")
        elif res.writecap == "budget":
            print("    writecap=budget  (integer authority)")
        if res.path_bound:
            print(f"    path={res.path_bound}")
        if res.fairness:
            extra = f" jain>={res.jain_min}" if res.jain_min is not None else ""
            print(f"    fairness={res.fairness}{extra}")
        if res.power and res.n_seeds is not None:
            print(f"    {power_cli_line(res.n_seeds)}")
        elif res.power == "low":
            print(
                f"    power=low  (n<{POWER_OK_MIN_SEEDS}  not journal; "
                "means ACCEPT still legal)"
            )
        elif res.power == "ok":
            print(f"    power=ok  (n>={POWER_OK_MIN_SEEDS})")
        if c.cuts_compose:
            print(f"    cuts_compose={c.cuts_compose}")
        if c.growth_compose:
            print(f"    growth_compose={c.growth_compose}")
        if res.compose_digest:
            print(f"    digest={res.compose_digest[:16]}")
        if res.authority:
            print(f"    authority={res.authority}")
        if res.views:
            print(f"    views={', '.join(res.views)}")
        if prog.contracts:
            print(f"    contract={prog.contracts[0].name} vs {prog.contracts[0].baseline}")
        return 0

    if args.cmd == "compile":
        try:
            out = compile_file(path, args.out)
        except TypeError as e:
            print(e)
            return 1
        print(f"wrote {out}")
        return 0

    if args.cmd == "emit-rust":
        from vela.emit_rust import emit_rust

        res = check(prog)
        if not res.ok:
            for e in res.errors:
                print(f"error: {e}")
            return 1
        text = emit_rust(prog)
        out = Path(args.out) if args.out else Path("emit") / f"{prog.controllers[0].name.lower()}.rs"
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_text(text, encoding="utf-8", newline="\n")
        print(f"wrote {out} (IR sketch, not a quiche controller)")
        return 0

    if args.cmd == "eval":
        res = check(prog)
        for w in res.warnings:
            print(f"warning: {w}")
        if not res.ok:
            for e in res.errors:
                print(f"error: {e}")
            return 1
        from vela.eval_harness import evaluate, write_result
        from vela.ir import program_to_config
        from vela.receipt import (
            build_receipt,
            eval_gate,
            gate_cli_line,
            resolve_eval_rails,
            verify_receipt,
            write_receipt,
        )

        view = getattr(args, "view", None)
        cfg = program_to_config(prog, view=view)
        seed_list = None
        if args.seeds:
            seed_list = [int(x) for x in args.seeds.split(",") if x.strip()]
        seeds, duration, scenarios, plan_errs = resolve_eval_rails(
            fast=args.fast,
            seeds=seed_list,
            duration_s=args.duration,
        )
        if plan_errs:
            for e in plan_errs:
                print(f"error: {e}")
            return 2
        run_seeds = seeds if seeds is not None else list(cfg.seeds)
        run_dur = duration if duration is not None else cfg.duration_s
        run_scen = scenarios if scenarios is not None else list(cfg.scenarios)
        planned = eval_gate(run_seeds, run_dur, run_scen)
        print(f"eval  controller={cfg.name}  {gate_cli_line(planned)}", flush=True)
        tag = args.tag or cfg.name.lower()
        summary = evaluate(
            cfg,
            seeds=seeds,
            scenarios=scenarios,
            duration_s=duration,
            include_oce=args.oce,
        )
        out = write_result(summary, tag=tag)
        receipt = build_receipt(
            source=src,
            source_name=str(path),
            compose=list(cfg.mechanisms),
            config=summary.get("config") or {},
            summary=summary,
        )
        rp = write_receipt(receipt, out.with_name(f"receipt_{tag}.json"))
        errs = verify_receipt(receipt, source=src, summary=summary)
        if errs:
            for e in errs:
                print(f"error: {e}")
            return 1
        dump_keys = [
            k
            for k in (
                "verdict",
                "power",
                "n_seeds",
                "journal",
                "gate",
                "asserts",
                "tables",
            )
            if k in summary
        ]
        print(json.dumps({k: summary[k] for k in dump_keys}, indent=2))
        # Eval summary line: power=low when n<8 without claiming journal significance.
        if summary.get("n_seeds") is not None:
            print(power_cli_line(int(summary["n_seeds"])))
        elif summary.get("power") == "low":
            print(f"power=low  (n<{POWER_OK_MIN_SEEDS}  not journal)")
        print(f"wrote {out}")
        print(
            f"receipt {rp}  {receipt['receipt_digest'][:16]}  "
            f"{gate_cli_line(str(summary.get('gate') or planned), summary.get('verdict'))}  "
            f"verified"
        )
        return 0 if summary["verdict"] == "ACCEPT" else 3

    return 1
