"""VELA command line."""
from __future__ import annotations

import argparse
import json
from pathlib import Path

from vela import __version__
from vela.checker import check
from vela.compile import compile_file, compile_source
from vela.parser import ParseError, parse


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(prog="vela", description="VELA compiler and eval")
    ap.add_argument("--version", action="version", version=f"VELA {__version__}")
    sub = ap.add_subparsers(dest="cmd", required=True)

    p_chk = sub.add_parser("check", help="parse + type-check")
    p_chk.add_argument("file")

    p_cmp = sub.add_parser("compile", help="lower to Python kernel config")
    p_cmp.add_argument("file")
    p_cmp.add_argument("-o", "--out", default=None)
    p_cmp.add_argument("--view", default=None)

    p_ev = sub.add_parser("eval", help="dual-gate eval on leo-aware-transport")
    p_ev.add_argument("file")
    p_ev.add_argument("--seeds", default=None)
    p_ev.add_argument("--fast", action="store_true", help="2 seeds, 45s, skip cubic")
    p_ev.add_argument("--duration", type=float, default=None)
    p_ev.add_argument("--oce", action="store_true")
    p_ev.add_argument("--tag", default="horizon")
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

        rec = json.loads(Path(args.file).read_text(encoding="utf-8"))
        src = None
        if args.source:
            src = Path(args.source).read_text(encoding="utf-8")
        errs = verify_receipt(rec, source=src)
        if errs:
            for e in errs:
                print(f"error: {e}")
            return 1
        print(f"ok  receipt={rec.get('receipt_digest', '')[:16]}  verdict={rec.get('verdict')}")
        return 0

    if not getattr(args, "file", None):
        print("file required")
        return 2

    path = Path(args.file)
    src = path.read_text(encoding="utf-8")
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
        from vela.receipt import build_receipt, write_receipt

        view = getattr(args, "view", None)
        cfg = program_to_config(prog, view=view)
        seeds = None
        duration = args.duration
        scenarios = None
        if args.fast:
            seeds = [13, 7]
            duration = duration or 45.0
            scenarios = ["leo_fast_ho", "terrestrial"]
        if args.seeds:
            seeds = [int(x) for x in args.seeds.split(",") if x.strip()]
        summary = evaluate(
            cfg,
            seeds=seeds,
            scenarios=scenarios,
            duration_s=duration,
            include_oce=args.oce,
        )
        out = write_result(summary, tag=args.tag)
        receipt = build_receipt(
            source=src,
            source_name=str(path),
            compose=list(cfg.mechanisms),
            config=summary.get("config") or {},
            summary=summary,
        )
        rp = write_receipt(receipt, out.with_name(f"receipt_{args.tag}.json"))
        print(json.dumps({k: summary[k] for k in ("verdict", "power", "asserts", "tables")}, indent=2))
        print(f"wrote {out}")
        print(f"receipt {rp}  {receipt['receipt_digest'][:16]}")
        return 0 if summary["verdict"] == "ACCEPT" else 3

    return 1
