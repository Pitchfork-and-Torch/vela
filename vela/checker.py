"""VELA static checker: freshness, loss coverage, compose cuts, contracts."""
from __future__ import annotations

from vela.ast import Controller, Program, Stmt, View
from vela.digest import compose_digest
from vela.types import (
    INTEGRATOR_OPS,
    LOSS_KINDS,
    RECONFIG_KINDS,
    STDLIB_MECHANISMS,
    WRITE_TARGETS,
    CheckResult,
)


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
    for v in prog.views:
        _check_view(v, prog, res)
    res.views = [v.name for v in prog.views]
    if prog.controllers:
        res.compose_digest = compose_digest(prog.controllers[0].compose)
        res.authority = dict(prog.controllers[0].authority)
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


def _check_view(v: View, prog: Program, res: CheckResult) -> None:
    names = {c.name for c in prog.controllers}
    if v.of_controller not in names:
        res.ok = False
        res.errors.append(f"view {v.name}: unknown controller {v.of_controller}")
    unknown = [m for m in v.compose if m not in STDLIB_MECHANISMS]
    for m in unknown:
        res.ok = False
        res.errors.append(f"view {v.name}: unknown mechanism {m}")


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

    reconf_ons = [o for o in c.ons if o.event == "Reconfig"]
    for o in reconf_ons:
        if o.match_arms:
            pats = {a.pattern for a in o.match_arms}
            missing = [k for k in RECONFIG_KINDS if k not in pats]
            extra = [p for p in pats if p not in RECONFIG_KINDS]
            if missing:
                res.ok = False
                res.errors.append(
                    f"{c.name}: Reconfig match missing {missing} (taxonomy must be closed)"
                )
            for p in extra:
                res.ok = False
                res.errors.append(f"{c.name}: unknown reconfig kind {p}")

    for o in c.ons:
        _check_stale_in_stmts(c.name, o.body, res)
        _check_cuts_in_stmts(c.name, o.body, res)
        for arm in o.match_arms:
            _check_cuts_in_stmts(c.name, arm.body, res)
    for w in c.whens:
        _check_stale_in_stmts(c.name, w.body, res)
        _check_cuts_in_stmts(c.name, w.body, res)
        _check_integrator(c.name, w, res)
    for e in c.everys:
        _check_stale_in_stmts(c.name, e.body, res)
        _check_cuts_in_stmts(c.name, e.body, res)

    _check_write_cap(c, res)


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


def _flatten_stmts(stmts: list[Stmt]) -> list[Stmt]:
    out: list[Stmt] = []
    for st in stmts:
        out.append(st)
        if st.body:
            out.extend(_flatten_stmts(st.body))
        extra = [x for x in st.args if isinstance(x, Stmt)]
        if extra:
            out.extend(_flatten_stmts(extra))
        # require else-bodies live in args as a list of Stmt
        nested: list[Stmt] = []
        for a in st.args:
            if isinstance(a, list) and a and isinstance(a[0], Stmt):
                nested.extend(a)
        if nested:
            out.extend(_flatten_stmts(nested))
    return out


def _check_integrator(cname: str, when, res: CheckResult) -> None:
    for st in _flatten_stmts(when.body):
        if st.kind != "assign" or not st.args:
            continue
        op = str(st.args[0])
        if op in INTEGRATOR_OPS and not when.integrate:
            res.ok = False
            res.errors.append(
                f"{cname}: when-body is a level; `{st.name} {op}` is an integrator "
                f"(Horizon seed 7: 55/173). Write `integrate when` to opt in."
            )
        if op in INTEGRATOR_OPS and when.integrate:
            res.warnings.append(
                f"{cname}: integrate when opted into a per-ACK {op} on {st.name}"
            )


def _lit_num(expr) -> float | None:
    if expr is None:
        return None
    if expr.kind == "num":
        raw = str(expr.value)
        for suf in ("Mbps", "ms", "s"):
            if raw.endswith(suf):
                raw = raw[: -len(suf)]
        try:
            return float(raw)
        except ValueError:
            return None
    return None


def _check_cuts_in_stmts(cname: str, stmts: list[Stmt], res: CheckResult) -> None:
    for st in _flatten_stmts(stmts):
        if st.kind != "cut":
            continue
        n = _lit_num(st.expr)
        if n is None:
            continue
        if not (0.0 < n <= 1.0):
            res.ok = False
            res.errors.append(
                f"{cname}: cut({n}) is outside (0, 1] (refinement law)"
            )


def _check_write_cap(c: Controller, res: CheckResult) -> None:
    caps = [s for s in c.signals if s.typ.name == "WriteCap"]
    if not caps:
        return
    writes = 0
    bodies = [w.body for w in c.whens] + [e.body for e in c.everys]
    for body in bodies:
        for st in _flatten_stmts(body):
            if st.kind == "chase":
                writes += 1
            elif st.kind == "assign" and st.name in WRITE_TARGETS:
                writes += 1
    budget = 0
    for s in caps:
        target = s.typ.inner.name if s.typ.inner is not None else "cwnd"
        budget = max(budget, int(c.authority.get(target, 0)))
    if writes > budget:
        res.ok = False
        res.errors.append(
            f"{c.name}: WriteCap exhausted ({writes} writes, budget {budget}). "
            f"No ambient authority. Raise `authority` or remove the write."
        )
