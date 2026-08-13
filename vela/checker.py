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

    intervals = {s.name for s in c.signals if s.typ.name == "Interval"}
    for o in c.ons:
        _check_stale_in_stmts(c.name, o.body, res)
        _check_cuts_in_stmts(c.name, o.body, res)
        _check_interval_in_stmts(c.name, o.body, intervals, set(), res)
        for arm in o.match_arms:
            _check_cuts_in_stmts(c.name, arm.body, res)
            _check_interval_in_stmts(c.name, arm.body, intervals, set(), res)
    for w in c.whens:
        _check_stale_in_stmts(c.name, w.body, res)
        _check_cuts_in_stmts(c.name, w.body, res)
        _check_integrator(c.name, w, res)
        proved = _proved_n_ge_2(w.pred, intervals)
        _walk_interval_point(c.name, w.pred, intervals, set(), res)
        _check_interval_in_stmts(c.name, w.body, intervals, proved, res)
    for e in c.everys:
        _check_stale_in_stmts(c.name, e.body, res)
        _check_cuts_in_stmts(c.name, e.body, res)
        _check_interval_in_stmts(c.name, e.body, intervals, set(), res)

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


INTERVAL_COUNT_ATTRS = frozenset({"n", "e"})


def interval_point_error(cname: str, name: str) -> str:
    return (
        f"{cname}: Interval {name} used as a point requires {name}.n >= 2 "
        "(uncertainty law)"
    )


def _interval_n_subject(expr, intervals: set[str]) -> str | None:
    """Return the Interval name if expr is `{name}.n`, or '*' for a bare `n`."""
    if expr is None:
        return None
    if expr.kind == "attr" and expr.name == "n" and expr.left is not None:
        if expr.left.kind == "name" and expr.left.name in intervals:
            return expr.left.name
        return None
    if expr.kind == "name" and expr.name == "n":
        return "*"
    return None


def _proved_n_ge_2(expr, intervals: set[str]) -> set[str]:
    """Names whose sample count is proved >= 2 by a comparison predicate."""
    out: set[str] = set()
    if expr is None or expr.kind != "binop" or not intervals:
        return out
    op = expr.name
    left, right = expr.left, expr.right
    sub_l = _interval_n_subject(left, intervals)
    sub_r = _interval_n_subject(right, intervals)
    num_l = _lit_num(left)
    num_r = _lit_num(right)

    def add(subject: str | None) -> None:
        if subject == "*":
            out.update(intervals)
        elif subject:
            out.add(subject)

    if sub_l is not None and num_r is not None:
        if (op == ">=" and num_r >= 2) or (op == ">" and num_r >= 1):
            add(sub_l)
    if sub_r is not None and num_l is not None:
        if (op == "<=" and num_l >= 2) or (op == "<" and num_l >= 1):
            add(sub_r)
    return out


def _stmt_else_body(st: Stmt) -> list[Stmt]:
    if st.args and isinstance(st.args[0], Stmt):
        return list(st.args)  # type: ignore[arg-type]
    return []


def _walk_enter_args(cname: str, args: list, intervals: set[str], proved: set[str], res: CheckResult) -> None:
    for a in args:
        if isinstance(a, tuple) and len(a) == 2:
            _walk_interval_point(cname, a[1], intervals, proved, res)
        else:
            _walk_interval_point(cname, a, intervals, proved, res)


def _check_interval_in_stmts(
    cname: str,
    stmts: list[Stmt],
    intervals: set[str],
    proved: set[str],
    res: CheckResult,
) -> None:
    if not intervals:
        return
    for st in stmts:
        if st.kind in ("assign", "let", "chase", "cut") and st.expr is not None:
            _walk_interval_point(cname, st.expr, intervals, proved, res)
        if st.kind == "chase":
            for a in st.args:
                _walk_interval_point(cname, a, intervals, proved, res)
        if st.kind == "freeze" and st.expr is not None:
            _walk_interval_point(cname, st.expr, intervals, proved, res)
        if st.kind == "enter":
            _walk_enter_args(cname, st.args, intervals, proved, res)
        if st.kind in ("when", "if", "require"):
            extra = proved | _proved_n_ge_2(st.expr, intervals)
            _walk_interval_point(cname, st.expr, intervals, proved, res)
            _check_interval_in_stmts(cname, st.body, intervals, extra, res)
            else_body = _stmt_else_body(st)
            if else_body:
                _check_interval_in_stmts(cname, else_body, intervals, proved, res)
        elif st.body:
            _check_interval_in_stmts(cname, st.body, intervals, proved, res)


def _walk_interval_point(
    cname: str,
    expr,
    intervals: set[str],
    proved: set[str],
    res: CheckResult,
) -> None:
    if expr is None or not hasattr(expr, "kind"):
        return
    if expr.kind == "name" and expr.name in intervals:
        if expr.name not in proved:
            res.ok = False
            res.errors.append(interval_point_error(cname, expr.name))
        return
    if expr.kind == "attr" and expr.left is not None and expr.left.kind == "name":
        base = expr.left.name
        if base in intervals:
            if expr.name in INTERVAL_COUNT_ATTRS:
                return
            # .lo / .mid / .hi (and any other field) is a point estimate.
            if base not in proved:
                res.ok = False
                res.errors.append(interval_point_error(cname, base))
            return
    if expr.kind == "call" and expr.left is not None and expr.left.kind == "name":
        # Interval.method(...) reads the interval, not a point estimate.
        if expr.left.name in intervals:
            for a in expr.args:
                _walk_interval_point(cname, a, intervals, proved, res)
            return
    _walk_interval_point(cname, expr.left, intervals, proved, res)
    _walk_interval_point(cname, expr.right, intervals, proved, res)
    for a in expr.args:
        _walk_interval_point(cname, a, intervals, proved, res)
