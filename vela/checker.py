"""VELA static checker: freshness, loss coverage, compose cuts, contracts."""
from __future__ import annotations

from vela.ast import Controller, Program, Stmt, View
from vela.digest import compose_digest
from vela.types import (
    HINT_ARMS,
    HINT_CHANNELS,
    HINT_TYPE_NAMES,
    HOUSE_ENDPOINT_CUT,
    INTEGRATOR_OPS,
    UNKNOWN_DELAY_RATIO,
    LOSS_KINDS,
    RECONFIG_KINDS,
    STDLIB_MECHANISMS,
    STDLIB_MODULES,
    WRITE_TARGETS,
    CheckResult,
    is_observe_only,
    review_writes_in,
)

# Check-time cwnd raisers. Closed-write operators stay off the packet path
# unless an author names them; two still need an explicit growth combinator.
CWND_RAISERS = ("OCE", "HorizonChase", "TrimFill", "QuietReach", "TrimReclaim")


def check(prog: Program) -> CheckResult:
    res = CheckResult(ok=True)
    if not prog.controllers:
        res.ok = False
        res.errors.append("no controller defined")
        return res
    if len(prog.controllers) > 1:
        res.warnings.append("multiple controllers; eval uses the first")
    for u in prog.uses:
        if u not in STDLIB_MODULES:
            res.ok = False
            res.errors.append(f"unknown module {u} (use only named stdlib surfaces)")
    for c in prog.controllers:
        _check_controller(c, prog, res)
    for v in prog.views:
        _check_view(v, prog, res)
    res.views = [v.name for v in prog.views]
    if prog.controllers:
        first = prog.controllers[0]
        res.compose_digest = compose_digest(first.compose)
        res.authority = dict(first.authority)
        res.posture = first.posture
        res.closed_writes = review_writes_in(first.compose)
        res.observe_only = first.posture == "observe" and is_observe_only(first.compose)
        res.hint_fail_closed = _has_hint_surface(first)
        res.typed_reconfig = _has_typed_reconfig(first)
        res.typed_loss = _has_typed_loss(first)
        res.passthrough = controller_is_passthrough(first)
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
    parent = next((c for c in prog.controllers if c.name == v.of_controller), None)
    if parent is not None and parent.posture == "observe":
        sneaks = review_writes_in(v.compose)
        if sneaks:
            res.ok = False
            res.errors.append(closed_write_error(f"view {v.name}", sneaks))


def _check_controller(c: Controller, prog: Program, res: CheckResult) -> None:
    unknown = [m for m in c.compose if m not in STDLIB_MECHANISMS]
    for m in unknown:
        res.ok = False
        res.errors.append(f"{c.name}: unknown mechanism {m}")
    res.mechanisms.extend(m for m in c.compose if m in STDLIB_MECHANISMS)

    writes = review_writes_in(c.compose)
    if c.posture == "observe" and writes:
        res.ok = False
        res.errors.append(closed_write_error(c.name, writes))
    elif c.posture == "review" and writes:
        res.warnings.append(
            f"{c.name}: posture review; closed-write {writes} stay off the "
            "packet path (ablation only)"
        )
    elif c.posture == "review" and not writes:
        res.warnings.append(
            f"{c.name}: posture review with no closed-write operator "
            "(flagship Reach is observe)"
        )

    hard = [m for m in c.compose if STDLIB_MECHANISMS.get(m, {}).get("cuts") == "hard"]
    # SoftReprobe + TypedLoss both hard-cut but on different events (epoch vs loss).
    # Same-event double hard-cut is the error unless the author picks min.
    epoch_hard = [m for m in hard if STDLIB_MECHANISMS[m]["phase"] == "epoch"]
    if len(epoch_hard) > 1 and c.cuts_compose != "min":
        res.ok = False
        res.errors.append(
            f"{c.name}: two hard epoch cuts {epoch_hard} (compose cuts = min to allow)"
        )

    raisers = [m for m in c.compose if m in CWND_RAISERS]
    if len(raisers) > 1 and c.growth_compose is None:
        res.ok = False
        res.errors.append(
            f"{c.name}: two cwnd raisers {raisers} "
            f"(compose growth = min | max | sum to allow)"
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
        if not o.match_arms:
            if c.posture == "observe":
                res.ok = False
                res.errors.append(typed_loss_error(c.name))
            continue
        pats = {a.pattern for a in o.match_arms}
        missing = [k for k in LOSS_KINDS if k not in pats]
        extra = [p for p in pats if p not in LOSS_KINDS]
        if missing:
            res.ok = False
            res.errors.append(
                f"{c.name}: Loss match missing {missing} (taxonomy must be closed)"
            )
        for p in extra:
            res.ok = False
            res.errors.append(f"{c.name}: unknown loss kind {p}")
        if c.posture == "observe":
            for arm in o.match_arms:
                _check_observe_loss_arm(c.name, arm, res)
        for arm in o.match_arms:
            _check_stale_in_stmts(c.name, arm.body, res)
        _check_stale_in_stmts(c.name, o.body, res)

    reconf_ons = [o for o in c.ons if o.event == "Reconfig"]
    for o in reconf_ons:
        if not o.match_arms:
            if c.posture == "observe":
                res.ok = False
                res.errors.append(typed_reconfig_error(c.name))
            continue
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
        if c.posture == "observe":
            _check_house_cut_in_stmts(c.name, o.body, res)
            for arm in o.match_arms:
                _check_house_cut_in_stmts(c.name, arm.body, res)

    _check_passthrough_cruise(c, res)
    _check_hint_surface(c, prog, res)
    hints = _hint_names(c)

    intervals = {s.name for s in c.signals if s.typ.name == "Interval"}
    for o in c.ons:
        _check_stale_in_stmts(c.name, o.body, res)
        _check_cuts_in_stmts(c.name, o.body, res)
        _check_interval_in_stmts(c.name, o.body, intervals, set(), res)
        _check_hint_in_stmts(c.name, o.body, hints, set(), res)
        _check_prior_min_rtt(c.name, o.body, res)
        for arm in o.match_arms:
            arm_proved = set(hints) if o.event == "Hint" and arm.pattern == "Some" else set()
            if o.event != "Loss":
                _check_stale_in_stmts(c.name, arm.body, res)
            _check_cuts_in_stmts(c.name, arm.body, res)
            _check_interval_in_stmts(c.name, arm.body, intervals, set(), res)
            _check_hint_in_stmts(c.name, arm.body, hints, arm_proved, res)
            _check_prior_min_rtt(c.name, arm.body, res)
    for w in c.whens:
        _check_stale_in_stmts(c.name, w.body, res)
        _check_cuts_in_stmts(c.name, w.body, res)
        _check_integrator(c.name, w, res)
        proved = _proved_n_ge_2(w.pred, intervals)
        _walk_interval_point(c.name, w.pred, intervals, set(), res)
        _check_interval_in_stmts(c.name, w.body, intervals, proved, res)
        hinted = _proved_hints(w.pred, hints)
        if not _is_hint_presence(w.pred, hints):
            _walk_hint_act(c.name, w.pred, hints, set(), res)
        _check_hint_in_stmts(c.name, w.body, hints, hinted, res)
        _check_prior_min_rtt(c.name, w.body, res)
    for e in c.everys:
        _check_stale_in_stmts(c.name, e.body, res)
        _check_cuts_in_stmts(c.name, e.body, res)
        _check_interval_in_stmts(c.name, e.body, intervals, set(), res)
        _check_hint_in_stmts(c.name, e.body, hints, set(), res)
        _check_prior_min_rtt(c.name, e.body, res)

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


def closed_write_error(cname: str, writes: list[str]) -> str:
    return (
        f"{cname}: closed-write {writes} require posture review "
        "(observe-only compose; no control-loop write)"
    )


def typed_reconfig_error(cname: str) -> str:
    return (
        f"{cname}: observe-only Reconfig must match RttHop | Flicker "
        "(typed reconfig; hop and flicker are not the same event)"
    )


def typed_loss_error(cname: str) -> str:
    return (
        f"{cname}: observe-only Loss must match Mobility | Congestive | Unknown "
        "(typed loss; recovery is type-directed)"
    )


def mobility_cut_error(cname: str) -> str:
    return (
        f"{cname}: observe-only Mobility must hold "
        "(typed loss; mobility is not congestive)"
    )


def unknown_cut_error(cname: str) -> str:
    return (
        f"{cname}: observe-only Unknown cut requires delay_ratio > {UNKNOWN_DELAY_RATIO} "
        "(typed loss; fall-through)"
    )


def house_cut_error(cname: str, n: float) -> str:
    return (
        f"{cname}: observe-only Reprobe cut({n}) must be {HOUSE_ENDPOINT_CUT} "
        "(house endpoint; SoftFlicker is review)"
    )


def cruise_write_error(cname: str, what: str) -> str:
    return (
        f"{cname}: observe-only cruise write `{what}` "
        "(passthrough; LeoAware wrap; no packet-path write)"
    )


def _cruise_write_label(st: Stmt) -> str | None:
    if st.kind == "assign" and st.name in WRITE_TARGETS:
        op = str(st.args[0]) if st.args else "="
        return f"{st.name} {op}"
    if st.kind == "chase":
        return "chase"
    if st.kind == "cut":
        return "cut"
    if st.kind == "enter":
        return f"enter {st.name}" if st.name else "enter"
    return None


def controller_cruise_writes(c: Controller) -> list[str]:
    found: list[str] = []
    bodies = [w.body for w in c.whens] + [e.body for e in c.everys]
    for body in bodies:
        for st in _flatten_stmts(body):
            label = _cruise_write_label(st)
            if label:
                found.append(label)
    return found


def controller_is_passthrough(c: Controller) -> bool:
    return (
        c.posture == "observe"
        and is_observe_only(c.compose)
        and _has_typed_reconfig(c)
        and _has_typed_loss(c)
        and not controller_cruise_writes(c)
    )


def _check_passthrough_cruise(c: Controller, res: CheckResult) -> None:
    if c.posture != "observe":
        return
    seen: set[str] = set()
    for label in controller_cruise_writes(c):
        if label in seen:
            continue
        seen.add(label)
        res.ok = False
        res.errors.append(cruise_write_error(c.name, label))


def _has_typed_reconfig(c: Controller) -> bool:
    reconf = [o for o in c.ons if o.event == "Reconfig"]
    if not reconf:
        return False
    for o in reconf:
        if not o.match_arms:
            return False
        pats = {a.pattern for a in o.match_arms}
        if any(k not in pats for k in RECONFIG_KINDS):
            return False
    return True


def controller_has_typed_loss(c: Controller) -> bool:
    return _has_typed_loss(c)


def _has_typed_loss(c: Controller) -> bool:
    loss = [o for o in c.ons if o.event == "Loss"]
    if not loss:
        return False
    for o in loss:
        if not o.match_arms:
            return False
        pats = {a.pattern for a in o.match_arms}
        if any(k not in pats for k in LOSS_KINDS):
            return False
    return True


def _is_recovery_cut(st: Stmt) -> bool:
    if st.kind == "cut":
        return True
    if st.kind == "enter" and st.name == "Reprobe":
        return True
    return False


def _stmts_have_cut(stmts: list[Stmt]) -> bool:
    return any(_is_recovery_cut(st) for st in _flatten_stmts(stmts))


def _is_delay_ratio_name(expr) -> bool:
    return expr is not None and getattr(expr, "kind", None) == "name" and expr.name == "delay_ratio"


def _proved_delay_ratio(expr) -> bool:
    """True when expr proves delay_ratio > UNKNOWN_DELAY_RATIO."""
    if expr is None or getattr(expr, "kind", None) != "binop":
        return False
    op = expr.name
    left, right = expr.left, expr.right
    num_l = _lit_num(left)
    num_r = _lit_num(right)
    if _is_delay_ratio_name(left) and num_r is not None:
        if op == ">" and num_r + 1e-12 >= UNKNOWN_DELAY_RATIO:
            return True
        if op == ">=" and num_r > UNKNOWN_DELAY_RATIO + 1e-12:
            return True
    if _is_delay_ratio_name(right) and num_l is not None:
        if op == "<" and num_l + 1e-12 >= UNKNOWN_DELAY_RATIO:
            return True
        if op == "<=" and num_l > UNKNOWN_DELAY_RATIO + 1e-12:
            return True
    return False


def _check_unknown_cuts(
    cname: str,
    stmts: list[Stmt],
    proved: bool,
    res: CheckResult,
) -> None:
    for st in stmts:
        if _is_recovery_cut(st) and not proved:
            res.ok = False
            res.errors.append(unknown_cut_error(cname))
        if st.kind in ("when", "if", "require"):
            extra = proved or _proved_delay_ratio(st.expr)
            _check_unknown_cuts(cname, st.body, extra, res)
            else_body = _stmt_else_body(st)
            if else_body:
                _check_unknown_cuts(cname, else_body, proved, res)
        elif st.body:
            _check_unknown_cuts(cname, st.body, proved, res)


def _check_observe_loss_arm(cname: str, arm, res: CheckResult) -> None:
    if arm.pattern == "Mobility":
        if _stmts_have_cut(arm.body):
            res.ok = False
            res.errors.append(mobility_cut_error(cname))
    elif arm.pattern == "Unknown":
        _check_unknown_cuts(cname, arm.body, False, res)


def _reprobe_cut(st: Stmt) -> float | None:
    if st.kind != "enter" or st.name != "Reprobe":
        return None
    for a in st.args:
        if isinstance(a, tuple) and len(a) == 2 and a[0] == "cut":
            return _lit_num(a[1])
    return None


def _check_house_cut_in_stmts(cname: str, stmts: list[Stmt], res: CheckResult) -> None:
    for st in _flatten_stmts(stmts):
        n = _reprobe_cut(st)
        if n is not None and abs(n - HOUSE_ENDPOINT_CUT) > 1e-9:
            res.ok = False
            res.errors.append(house_cut_error(cname, n))
        if st.kind == "cut":
            cn = _lit_num(st.expr)
            if cn is not None and abs(cn - HOUSE_ENDPOINT_CUT) > 1e-9:
                res.ok = False
                res.errors.append(house_cut_error(cname, cn))


def hint_law_error(cname: str, name: str) -> str:
    return (
        f"{cname}: Hint {name} used without a Some-proof "
        "(hint law; fail-closed)"
    )


def _has_hint_surface(c: Controller) -> bool:
    if any(o.event == "Hint" for o in c.ons):
        return True
    return any(s.typ.name in HINT_TYPE_NAMES for s in c.signals)


def _hint_names(c: Controller) -> set[str]:
    names = {s.name for s in c.signals if s.typ.name in HINT_TYPE_NAMES}
    if _has_hint_surface(c):
        names.add("hint")
        for o in c.ons:
            if o.event == "Hint" and o.binder:
                names.add(o.binder)
    return names


def _check_hint_surface(c: Controller, prog: Program, res: CheckResult) -> None:
    if not _has_hint_surface(c):
        return
    if "std.hint" not in prog.uses:
        res.ok = False
        res.errors.append(
            f"{c.name}: Hint requires `use std.hint` "
            "(fail-closed; no ambient hop oracle)"
        )
    hint_ons = [o for o in c.ons if o.event == "Hint"]
    for o in hint_ons:
        if not o.match_arms:
            res.ok = False
            res.errors.append(
                f"{c.name}: Hint must match Some | None "
                "(fail-closed; missing hint is not a hop oracle)"
            )
            continue
        pats = {a.pattern for a in o.match_arms}
        missing = [k for k in HINT_ARMS if k not in pats]
        extra = [p for p in pats if p not in HINT_ARMS]
        if missing:
            res.ok = False
            res.errors.append(
                f"{c.name}: Hint match missing {missing} (fail-closed)"
            )
        for p in extra:
            res.ok = False
            res.errors.append(f"{c.name}: unknown Hint arm {p} (expected Some | None)")


def _hint_subject_of(expr, hints: set[str]) -> str | None:
    if expr is None or not hasattr(expr, "kind"):
        return None
    if expr.kind == "name" and expr.name in hints:
        return expr.name
    if expr.kind == "attr" and expr.left is not None and expr.left.kind == "name":
        base = expr.left.name
        if base in hints:
            return base
        if base == "hint" and expr.name in HINT_CHANNELS and "hint" in hints:
            return "hint"
    if expr.kind == "attr" and expr.left is not None and expr.left.kind == "attr":
        return _hint_subject_of(expr.left, hints)
    return None


def _is_hint_presence(expr, hints: set[str]) -> bool:
    if expr is None or not hasattr(expr, "kind"):
        return False
    if expr.kind == "name" and expr.name in hints:
        return True
    if expr.kind == "attr" and expr.left is not None and expr.left.kind == "name":
        if expr.left.name in hints and expr.name in HINT_CHANNELS:
            return True
        if expr.left.name == "hint" and expr.name in HINT_CHANNELS and "hint" in hints:
            return True
    return False


def _proved_hints(expr, hints: set[str]) -> set[str]:
    if _is_hint_presence(expr, hints):
        sub = _hint_subject_of(expr, hints)
        return {sub} if sub else set()
    return set()


def _walk_hint_act(
    cname: str,
    expr,
    hints: set[str],
    proved: set[str],
    res: CheckResult,
) -> None:
    if expr is None or not hasattr(expr, "kind") or not hints:
        return
    sub = _hint_subject_of(expr, hints)
    if sub and sub not in proved:
        res.ok = False
        res.errors.append(hint_law_error(cname, sub))
        return
    _walk_hint_act(cname, expr.left, hints, proved, res)
    _walk_hint_act(cname, expr.right, hints, proved, res)
    for a in getattr(expr, "args", []) or []:
        _walk_hint_act(cname, a, hints, proved, res)


def _check_hint_in_stmts(
    cname: str,
    stmts: list[Stmt],
    hints: set[str],
    proved: set[str],
    res: CheckResult,
) -> None:
    if not hints:
        return
    for st in stmts:
        if st.kind in ("assign", "let", "chase", "cut") and st.expr is not None:
            _walk_hint_act(cname, st.expr, hints, proved, res)
        if st.kind == "chase":
            for a in st.args:
                _walk_hint_act(cname, a, hints, proved, res)
        if st.kind == "freeze" and st.expr is not None:
            _walk_hint_act(cname, st.expr, hints, proved, res)
        if st.kind == "enter":
            for a in st.args:
                if isinstance(a, tuple) and len(a) == 2:
                    _walk_hint_act(cname, a[1], hints, proved, res)
                else:
                    _walk_hint_act(cname, a, hints, proved, res)
        if st.kind in ("when", "if", "require"):
            extra = proved | _proved_hints(st.expr, hints)
            if not _is_hint_presence(st.expr, hints):
                _walk_hint_act(cname, st.expr, hints, proved, res)
            _check_hint_in_stmts(cname, st.body, hints, extra, res)
            else_body = _stmt_else_body(st)
            if else_body:
                _check_hint_in_stmts(cname, else_body, hints, proved, res)
        elif st.body:
            _check_hint_in_stmts(cname, st.body, hints, proved, res)


def _expr_has_prior_min_rtt(expr) -> bool:
    if expr is None or not hasattr(expr, "kind"):
        return False
    if (
        expr.kind == "attr"
        and expr.name == "min_rtt"
        and expr.left is not None
        and expr.left.kind == "name"
        and expr.left.name == "prior"
    ):
        return True
    if _expr_has_prior_min_rtt(expr.left) or _expr_has_prior_min_rtt(expr.right):
        return True
    return any(_expr_has_prior_min_rtt(a) for a in getattr(expr, "args", []) or [])


def _check_prior_min_rtt(cname: str, stmts: list[Stmt], res: CheckResult) -> None:
    for st in _flatten_stmts(stmts):
        if st.kind == "assign" and st.name == "min_rtt" and _expr_has_prior_min_rtt(st.expr):
            res.ok = False
            res.errors.append(
                f"{cname}: cannot write min_rtt from prior.min_rtt (freshness law)"
            )


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
