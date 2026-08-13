"""VELA static checker: freshness, loss coverage, compose cuts, contracts."""
from __future__ import annotations

from vela.ast import Controller, Program, Stmt
from vela.types import LOSS_KINDS, STDLIB_MECHANISMS, CheckResult


def check(prog: Program) -> CheckResult:
    res = CheckResult(ok=True)
    if not prog.controllers:
        res.ok = False
        res.errors.append("no controller defined")
        return res
    if len(prog.controllers) > 1:
        res.warnings.append("multiple controllers; eval uses the first")
    for c in prog.controllers:
        _check_controller(c, res)
    for con in prog.contracts:
        if not con.seeds:
            res.ok = False
            res.errors.append(f"contract {con.name}: empty seeds")
        if "leo_fast_ho" not in con.scenarios and not any(
            a.left.startswith("terrestrial") for a in con.asserts
        ):
            res.warnings.append(
                f"contract {con.name}: no leo_fast_ho scenario and no terrestrial assert"
            )
        if len(con.seeds) < 5:
            res.warnings.append(
                f"contract {con.name}: {len(con.seeds)} seeds (power=low for p-values)"
            )
        terr = [a for a in con.asserts if "terrestrial" in a.left]
        if not terr:
            res.warnings.append(
                f"contract {con.name}: missing terrestrial assert (INCOMPLETE if not added)"
            )
    return res


def _check_controller(c: Controller, res: CheckResult) -> None:
    unknown = [m for m in c.compose if m not in STDLIB_MECHANISMS]
    for m in unknown:
        res.ok = False
        res.errors.append(f"{c.name}: unknown mechanism {m}")
    res.mechanisms.extend(m for m in c.compose if m in STDLIB_MECHANISMS)

    hard = [m for m in c.compose if STDLIB_MECHANISMS.get(m, {}).get("cuts") == "hard"]
    # SoftReprobe + TypedLoss both hard-cut but on different events (epoch vs loss).
    # Same-event double hard-cut is the error.
    epoch_hard = [m for m in hard if STDLIB_MECHANISMS[m]["phase"] == "epoch"]
    if len(epoch_hard) > 1:
        res.ok = False
        res.errors.append(
            f"{c.name}: two hard epoch cuts {epoch_hard} (compose cuts = min to allow)"
        )

    # OCE + HorizonChase both write cwnd on ack (soft). Warn: pick one chase.
    if "OCE" in c.compose and "HorizonChase" in c.compose:
        res.warnings.append(
            f"{c.name}: OCE and HorizonChase both chase; HorizonChase should replace OCE"
        )
    if "HorizonChase" in c.compose and "TrimFill" in c.compose:
        res.warnings.append(
            f"{c.name}: HorizonChase and TrimFill both fill; pick one"
        )
    if "QuietReach" in c.compose and "HorizonChase" in c.compose:
        res.warnings.append(
            f"{c.name}: QuietReach and HorizonChase both write cwnd; pick one"
        )
    if "QuietReach" in c.compose and "TrimFill" in c.compose:
        res.warnings.append(
            f"{c.name}: QuietReach and TrimFill both fill; QuietReach is the apoapsis write"
        )
    if "QuietReach" in c.compose and "TrimReclaim" in c.compose:
        res.warnings.append(
            f"{c.name}: QuietReach and TrimReclaim both add cwnd; reclaim dumped seed 7"
        )
    if "QuietReach" in c.compose and "IntervalBw" not in c.compose:
        res.warnings.append(f"{c.name}: QuietReach without IntervalBw uses point bw")
    if "QuietShield" in c.compose and "Calendar" not in c.compose:
        res.warnings.append(
            f"{c.name}: QuietShield without Calendar cannot see HO-scale gaps"
        )
    if "QuietShield" in c.compose and "SoftFlicker" in c.compose:
        res.warnings.append(
            f"{c.name}: QuietShield refuses the detect; SoftFlicker needs it to fire"
        )

    if "IntervalBw" not in c.compose and "HorizonChase" in c.compose:
        res.warnings.append(f"{c.name}: HorizonChase without IntervalBw uses point bw")

    sig_names = {s.name for s in c.signals}
    for s in c.signals:
        if s.typ.at_epoch and s.typ.at_epoch not in sig_names and s.typ.at_epoch != "epoch":
            res.warnings.append(
                f"{c.name}: signal {s.name} bound to unknown epoch name {s.typ.at_epoch}"
            )
        if s.typ.name in ("Sample", "Interval") and not s.typ.at_epoch:
            res.ok = False
            res.errors.append(
                f"{c.name}: {s.typ.name} {s.name} must be tagged @ epoch (freshness law)"
            )

    loss_ons = [o for o in c.ons if o.event == "Loss"]
    for o in loss_ons:
        if o.match_arms:
            pats = {a.pattern for a in o.match_arms}
            missing = [k for k in LOSS_KINDS if k not in pats]
            if missing:
                res.ok = False
                res.errors.append(
                    f"{c.name}: Loss match missing {missing} (taxonomy must be closed)"
                )
        for arm in o.match_arms:
            _check_stale_in_stmts(c.name, arm.body, res)
        _check_stale_in_stmts(c.name, o.body, res)

    for o in c.ons:
        _check_stale_in_stmts(c.name, o.body, res)
    for w in c.whens:
        _check_stale_in_stmts(c.name, w.body, res)
    for e in c.everys:
        _check_stale_in_stmts(c.name, e.body, res)


def _check_stale_in_stmts(cname: str, stmts: list[Stmt], res: CheckResult) -> None:
    invalidated: set[str] = set()
    for st in stmts:
        if st.kind == "invalidate":
            invalidated.update(str(a) for a in st.args)
        if st.kind == "let" and st.expr is not None:
            _walk_stale(cname, st.expr, invalidated, res)
        if st.kind == "chase" and st.expr is not None:
            _walk_stale(cname, st.expr, invalidated, res)
        if st.kind == "assign" and st.expr is not None:
            _walk_stale(cname, st.expr, invalidated, res)
        if st.body:
            _check_stale_in_stmts(cname, st.body, res)


def _walk_stale(cname: str, expr, invalidated: set[str], res: CheckResult) -> None:
    if expr is None:
        return
    if expr.kind == "name" and expr.name in invalidated:
        res.ok = False
        res.errors.append(
            f"{cname}: read of invalidated sample {expr.name} (freshness law)"
        )
    if expr.kind == "attr" and expr.left is not None and expr.left.kind == "name":
        if expr.left.name in invalidated:
            res.ok = False
            res.errors.append(
                f"{cname}: read of invalidated {expr.left.name}.{expr.name}"
            )
    _walk_stale(cname, expr.left, invalidated, res)
    _walk_stale(cname, expr.right, invalidated, res)
    for a in expr.args:
        _walk_stale(cname, a, invalidated, res)
