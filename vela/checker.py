"""VELA static checker: freshness, loss coverage, compose cuts, contracts."""
from __future__ import annotations

from vela.ast import Controller, Program, Stmt, View
from vela.digest import compose_digest
from vela.ir import parse_report_ci
from vela.oracle import oracle_error, oracle_name_of
from vela.path import (
    house_mismatch_warning,
    parse_program_paths,
    path_digest,
    path_needs_std_error,
    unbound_path_warning,
)
from vela.types import (
    FAIRNESS_SCENARIO,
    HINT_ARMS,
    HINT_CHANNELS,
    HINT_TYPE_NAMES,
    HOUSE_ENDPOINT_CUT,
    PREDICTIVE_FREEZE_FIRE_STAMP,
    PREDICTIVE_FREEZE_MIN_HO_GAPS,
    HYBRID_JUMP_KINDS,
    HYBRID_MODES,
    HYBRID_TICKS,
    INTEGRATOR_OPS,
    KNOWN_SCENARIOS,
    POWER_OK_MIN_SEEDS,
    UNKNOWN_DELAY_RATIO,
    LOSS_KINDS,
    RECONFIG_KINDS,
    assert_names_jain,
    eval_power,
    parse_jain_floor,
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
        res.no_oracle = not _controller_mentions_oracle(first)
        res.cuts_compose = first.cuts_compose or ""
        if controller_stamps_predictive_freeze(first):
            res.predictive_freeze = PREDICTIVE_FREEZE_FIRE_STAMP
    _check_paths(prog, res)
    for con in prog.contracts:
        if not con.seeds:
            res.ok = False
            res.errors.append(f"contract {con.name}: empty seeds")
        # duration 0s (or negative) is not an eval window  -  check used to
        # accept it and stamp cfg.duration_s=0, so eval ran an empty episode.
        if con.duration_s is not None and float(con.duration_s) <= 0:
            res.ok = False
            res.errors.append(
                f"contract {con.name}: duration must be positive, got {con.duration_s:g}s"
            )
        if "leo_fast_ho" not in con.scenarios and not any(
            a.left.startswith("terrestrial") for a in con.asserts
        ):
            res.warnings.append(
                f"contract {con.name}: no leo_fast_ho scenario and no terrestrial assert"
            )
        n_seeds = len(con.seeds)
        if eval_power(n_seeds) == "low":
            res.warnings.append(power_low_warning(con.name, n_seeds))
        terr = [a for a in con.asserts if "terrestrial" in a.left]
        if not terr:
            res.warnings.append(
                f"contract {con.name}: missing terrestrial assert (INCOMPLETE if not added)"
            )
        _level, ci_errs = parse_report_ci(con.reports)
        for err in ci_errs:
            res.ok = False
            res.errors.append(f"contract {con.name}: {err}")
        _check_fairness_contract(con, res)
        for scen in con.scenarios:
            if scen not in KNOWN_SCENARIOS:
                res.warnings.append(
                    f"contract {con.name}: unknown scenario {scen} "
                    f"(known: {', '.join(sorted(KNOWN_SCENARIOS))})"
                )
    if prog.contracts:
        res.power = (
            "low"
            if any(eval_power(len(c.seeds)) == "low" for c in prog.contracts)
            else "ok"
        )
        first_con = prog.contracts[0]
        if FAIRNESS_SCENARIO in first_con.scenarios:
            res.fairness = FAIRNESS_SCENARIO
        for a in first_con.asserts:
            if assert_names_jain(a.left):
                res.jain_min = parse_jain_floor(a.right)
                break
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
    _check_oracle(c, res)
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
        _check_integrator(c.name, w.body, w.integrate, res, surface="when")
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
        _check_integrator(c.name, e.body, e.integrate, res, surface="every")
        _check_interval_in_stmts(c.name, e.body, intervals, set(), res)
        _check_hint_in_stmts(c.name, e.body, hints, set(), res)
        _check_prior_min_rtt(c.name, e.body, res)

    _check_nested_when_integrator(c, res)
    _check_write_cap(c, res)
    _check_affine(c, res)
    _check_hybrid(c, res)


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


def _check_integrator(
    cname: str,
    stmts: list[Stmt],
    integrate: bool,
    res: CheckResult,
    *,
    surface: str,
) -> None:
    opt = f"integrate {surface}"
    for st in _flatten_stmts(stmts):
        if st.kind != "assign" or not st.args:
            continue
        op = str(st.args[0])
        if op not in INTEGRATOR_OPS:
            continue
        if not integrate:
            res.ok = False
            res.errors.append(
                f"{cname}: {surface}-body is a level; `{st.name} {op}` is an integrator "
                f"(Horizon seed 7: 55/173). Write `{opt}` to opt in."
            )
        else:
            res.warnings.append(
                f"{cname}: {opt} opted into a per-ACK {op} on {st.name}"
            )


def _nested_when_stmts(stmts: list[Stmt]) -> list[Stmt]:
    out: list[Stmt] = []
    for st in stmts:
        if st.kind == "when":
            out.append(st)
        if st.body:
            out.extend(_nested_when_stmts(st.body))
        else_body = _stmt_else_body(st)
        if else_body:
            out.extend(_nested_when_stmts(else_body))
    return out


def _check_nested_when_integrator(c: Controller, res: CheckResult) -> None:
    """when-as-stmt inside on is still a level. Top-level when/every already flatten."""
    for o in c.ons:
        for nested in _nested_when_stmts(o.body):
            _check_integrator(c.name, nested.body, False, res, surface="when")
        for arm in o.match_arms:
            for nested in _nested_when_stmts(arm.body):
                _check_integrator(c.name, nested.body, False, res, surface="when")


def hybrid_jump_in_flow_error(cname: str, kind: str, surface: str) -> str:
    return (
        f"{cname}: `{kind}` is a discrete jump; {surface} is a flow "
        "(hybrid automata; write it in `on`)"
    )


def hybrid_unknown_mode_error(cname: str, name: str) -> str:
    return (
        f"{cname}: enter {name} is not a mode "
        "(hybrid automata; enter Reprobe)"
    )


def hybrid_tick_error(cname: str, tick: str) -> str:
    return (
        f"{cname}: every {tick} is not a sampled flow "
        "(hybrid automata; every ack | every epoch)"
    )


def _jump_label(st: Stmt) -> str:
    if st.kind == "enter":
        return f"enter {st.name}" if st.name else "enter"
    return st.kind


def _check_hybrid_flow(
    cname: str, stmts: list[Stmt], surface: str, res: CheckResult
) -> None:
    for st in _flatten_stmts(stmts):
        if st.kind not in HYBRID_JUMP_KINDS:
            continue
        res.ok = False
        res.hybrid = False
        err = hybrid_jump_in_flow_error(cname, _jump_label(st), surface)
        if err not in res.errors:
            res.errors.append(err)
        if st.kind == "enter" and st.name not in HYBRID_MODES:
            mode_err = hybrid_unknown_mode_error(cname, st.name or "?")
            if mode_err not in res.errors:
                res.errors.append(mode_err)


def _check_hybrid_jumps(cname: str, stmts: list[Stmt], res: CheckResult) -> None:
    for st in _flatten_stmts(stmts):
        if st.kind != "enter":
            continue
        if st.name in HYBRID_MODES:
            continue
        res.ok = False
        res.hybrid = False
        err = hybrid_unknown_mode_error(cname, st.name or "?")
        if err not in res.errors:
            res.errors.append(err)


def _check_hybrid(c: Controller, res: CheckResult) -> None:
    for w in c.whens:
        _check_hybrid_flow(c.name, w.body, "when", res)
    for e in c.everys:
        if e.tick not in HYBRID_TICKS:
            res.ok = False
            res.hybrid = False
            err = hybrid_tick_error(c.name, e.tick)
            if err not in res.errors:
                res.errors.append(err)
        _check_hybrid_flow(c.name, e.body, "every", res)
    for o in c.ons:
        _check_hybrid_jumps(c.name, o.body, res)
        for arm in o.match_arms:
            _check_hybrid_jumps(c.name, arm.body, res)


def affine_reuse_error(cname: str, name: str) -> str:
    return (
        f"{cname}: Sample {name} already used in this block "
        "(affine; bind with let, or prior after epoch edge)"
    )


def affine_epoch_error(cname: str, name: str) -> str:
    return (
        f"{cname}: Sample {name} @ e cannot be used after Reprobe "
        f"(e+1; name prior.{name})"
    )


def affine_mix_error(cname: str, name: str) -> str:
    return (
        f"{cname}: mixed {name} and prior.{name} in one expression "
        "(affine provenance; one epoch)"
    )


def _affine_names(c: Controller) -> set[str]:
    names = {"min_rtt", "bw"}
    for s in c.signals:
        if s.typ.name in ("Sample", "Interval"):
            names.add(s.name)
    return names


def _affine_attr(expr, affine: set[str]) -> tuple[str | None, bool, bool]:
    """Unroll attr chain. Return (base, from_prior, count_only)."""
    attrs: list[str] = []
    cur = expr
    while cur is not None and getattr(cur, "kind", None) == "attr":
        attrs.append(cur.name)
        cur = cur.left
    if cur is None or getattr(cur, "kind", None) != "name":
        return None, False, False
    fields = list(reversed(attrs))
    if cur.name == "prior":
        base = fields[0] if fields else None
        return base, True, False
    if cur.name in affine:
        if fields and fields[0] in INTERVAL_COUNT_ATTRS:
            return cur.name, False, True
        return cur.name, False, False
    return None, False, False


def _affine_walk(expr, affine: set[str]) -> tuple[set[str], set[str]]:
    """Current-epoch uses and prior. bases in expr."""
    uses: set[str] = set()
    priors: set[str] = set()
    if expr is None or not hasattr(expr, "kind"):
        return uses, priors
    if expr.kind == "name" and expr.name in affine:
        uses.add(expr.name)
        return uses, priors
    if expr.kind == "attr":
        base, from_prior, count_only = _affine_attr(expr, affine)
        if from_prior and base:
            priors.add(base)
            return uses, priors
        if base and count_only:
            return uses, priors
        if base:
            uses.add(base)
            return uses, priors
    u, p = _affine_walk(getattr(expr, "left", None), affine)
    uses |= u
    priors |= p
    u, p = _affine_walk(getattr(expr, "right", None), affine)
    uses |= u
    priors |= p
    for a in getattr(expr, "args", []) or []:
        u, p = _affine_walk(a, affine)
        uses |= u
        priors |= p
    return uses, priors


def _affine_note(
    cname: str,
    uses: set[str],
    priors: set[str],
    consumed: set[str],
    epoch_advanced: bool,
    res: CheckResult,
) -> None:
    for n in sorted(uses & priors):
        res.ok = False
        res.affine = False
        err = affine_mix_error(cname, n)
        if err not in res.errors:
            res.errors.append(err)
    for n in sorted(uses):
        if epoch_advanced:
            res.ok = False
            res.affine = False
            err = affine_epoch_error(cname, n)
        elif n in consumed:
            res.ok = False
            res.affine = False
            err = affine_reuse_error(cname, n)
        else:
            err = ""
        if err and err not in res.errors:
            res.errors.append(err)
        consumed.add(n)


def _affine_from_enter_args(args: list, affine: set[str]) -> tuple[set[str], set[str]]:
    uses: set[str] = set()
    priors: set[str] = set()
    for a in args:
        expr = a[1] if isinstance(a, tuple) and len(a) == 2 else a
        u, p = _affine_walk(expr, affine)
        uses |= u
        priors |= p
    return uses, priors


def _check_affine_in_stmts(
    cname: str,
    stmts: list[Stmt],
    affine: set[str],
    consumed: set[str],
    epoch_advanced: bool,
    res: CheckResult,
) -> tuple[set[str], bool]:
    live = set(affine)
    for st in stmts:
        uses: set[str] = set()
        priors: set[str] = set()
        if st.kind in ("assign", "let", "chase", "cut") and st.expr is not None:
            u, p = _affine_walk(st.expr, live)
            uses |= u
            priors |= p
        if st.kind == "chase":
            for a in st.args:
                u, p = _affine_walk(a, live)
                uses |= u
                priors |= p
        if st.kind == "freeze" and st.expr is not None:
            u, p = _affine_walk(st.expr, live)
            uses |= u
            priors |= p
        if st.kind == "enter":
            u, p = _affine_from_enter_args(st.args, live)
            uses |= u
            priors |= p
        if st.kind in ("when", "if", "require") and st.expr is not None:
            # Guards are not consumes. Mix with prior in the guard still errors.
            u, p = _affine_walk(st.expr, live)
            for n in sorted(u & p):
                res.ok = False
                res.affine = False
                err = affine_mix_error(cname, n)
                if err not in res.errors:
                    res.errors.append(err)
            then_cons = set(consumed)
            then_epoch = epoch_advanced
            then_cons, then_epoch = _check_affine_in_stmts(
                cname, st.body, live, then_cons, then_epoch, res
            )
            else_body = _stmt_else_body(st)
            else_cons = set(consumed)
            else_epoch = epoch_advanced
            if else_body:
                else_cons, else_epoch = _check_affine_in_stmts(
                    cname, else_body, live, else_cons, else_epoch, res
                )
            consumed = then_cons | else_cons
            epoch_advanced = then_epoch or else_epoch
            continue
        _affine_note(cname, uses, priors, consumed, epoch_advanced, res)
        if st.kind == "invalidate":
            for name in st.args:
                n = str(name)
                if n in live:
                    consumed.add(n)
        if st.kind == "enter" and st.name == "Reprobe":
            epoch_advanced = True
        if st.kind == "let" and st.name:
            live.discard(st.name)
        if st.body and st.kind not in ("when", "if", "require"):
            consumed, epoch_advanced = _check_affine_in_stmts(
                cname, st.body, live, consumed, epoch_advanced, res
            )
    return consumed, epoch_advanced


def _check_affine(c: Controller, res: CheckResult) -> None:
    affine = _affine_names(c)
    if not affine:
        return
    for o in c.ons:
        _check_affine_in_stmts(c.name, o.body, affine, set(), False, res)
        for arm in o.match_arms:
            _check_affine_in_stmts(c.name, arm.body, affine, set(), False, res)
    for w in c.whens:
        _check_affine_in_stmts(c.name, w.body, affine, set(), False, res)
    for e in c.everys:
        _check_affine_in_stmts(c.name, e.body, affine, set(), False, res)


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


def writecap_exhausted_error(cname: str, writes: int, budget: int) -> str:
    return (
        f"{cname}: WriteCap exhausted ({writes} writes, budget {budget}). "
        f"No ambient authority. Raise `authority` or remove the write."
    )


def writecap_ambient_error(cname: str, what: str) -> str:
    return (
        f"{cname}: cruise write `{what}` without borrow "
        "(WriteCap is linear; split/borrow)"
    )


def writecap_reuse_error(cname: str, name: str) -> str:
    return (
        f"{cname}: WriteCap {name} already consumed "
        "(linear; split or borrow once)"
    )


def writecap_unknown_error(cname: str, name: str) -> str:
    return (
        f"{cname}: unknown WriteCap {name} "
        "(declare WriteCap or split a parent into this name)"
    )


def writecap_target_error(cname: str, cap: str, target: str, got: str) -> str:
    return (
        f"{cname}: borrow {cap} is WriteCap<{target}>, cannot write {got} "
        "(linear target)"
    )


def writecap_split_sum_error(cname: str, parent: str, need: int, got: int) -> str:
    return (
        f"{cname}: split {parent} weights sum to {got}, parent budget {need} "
        "(linear; partition the budget)"
    )


def _cap_target(signal) -> str:
    if signal.typ.inner is not None:
        return signal.typ.inner.name
    return "cwnd"


def _is_cap_write(st: Stmt) -> str | None:
    if st.kind == "chase":
        return "chase"
    if st.kind == "assign" and st.name in WRITE_TARGETS:
        op = str(st.args[0]) if st.args else "="
        return f"{st.name} {op}"
    return None


def _write_target_of(st: Stmt) -> str | None:
    if st.kind == "chase":
        return st.name if st.name in WRITE_TARGETS else "cwnd"
    if st.kind == "assign" and st.name in WRITE_TARGETS:
        return st.name
    return None


def _collect_cap_traffic(
    stmts: list[Stmt],
    owner: str | None,
    borrows: dict[str, list[Stmt]],
    writes: list[tuple[str | None, Stmt]],
) -> None:
    for st in stmts:
        if st.kind == "borrow":
            borrows.setdefault(st.name, []).append(st)
            _collect_cap_traffic(st.body, st.name, borrows, writes)
            continue
        if _is_cap_write(st):
            writes.append((owner, st))
        if st.kind in ("when", "if", "require"):
            _collect_cap_traffic(st.body, owner, borrows, writes)
            else_body = _stmt_else_body(st)
            if else_body:
                _collect_cap_traffic(else_body, owner, borrows, writes)
        elif st.body:
            _collect_cap_traffic(st.body, owner, borrows, writes)


def _controller_bodies(c: Controller) -> list[list[Stmt]]:
    bodies = [w.body for w in c.whens] + [e.body for e in c.everys]
    bodies.extend(o.body for o in c.ons)
    for o in c.ons:
        bodies.extend(arm.body for arm in o.match_arms)
    return bodies


def _check_write_cap(c: Controller, res: CheckResult) -> None:
    caps = [s for s in c.signals if s.typ.name == "WriteCap"]
    borrows: dict[str, list[Stmt]] = {}
    writes: list[tuple[str | None, Stmt]] = []
    for body in _controller_bodies(c):
        _collect_cap_traffic(body, None, borrows, writes)
    linear = bool(c.splits) or bool(borrows)
    if not caps and not linear:
        return
    if not linear:
        n_writes = sum(1 for owner, _st in writes if owner is None)
        budget = 0
        for s in caps:
            target = _cap_target(s)
            budget = max(budget, int(c.authority.get(target, 0)))
        res.writecap = "budget"
        if n_writes > budget:
            res.ok = False
            res.errors.append(writecap_exhausted_error(c.name, n_writes, budget))
        return

    res.writecap = "linear"
    live: dict[str, tuple[str, int]] = {}
    consumed: set[str] = set()
    signal_names = {s.name for s in c.signals}
    for s in caps:
        live[s.name] = (_cap_target(s), int(c.authority.get(_cap_target(s), 0)))

    for sp in c.splits:
        if sp.parent in consumed:
            res.ok = False
            res.errors.append(writecap_reuse_error(c.name, sp.parent))
            continue
        if sp.parent not in live:
            res.ok = False
            res.errors.append(writecap_unknown_error(c.name, sp.parent))
            continue
        target, budget = live.pop(sp.parent)
        consumed.add(sp.parent)
        names = [n for n, _w in sp.children]
        weights = [w for _n, w in sp.children]
        if any(w is None for w in weights) and any(w is not None for w in weights):
            res.ok = False
            res.errors.append(
                f"{c.name}: split {sp.parent} mixes bare names and weights "
                "(linear; all 1 or all explicit)"
            )
            continue
        if all(w is None for w in weights):
            parts = [1] * len(names)
            if budget != len(names):
                res.ok = False
                res.errors.append(
                    writecap_split_sum_error(c.name, sp.parent, budget, len(names))
                )
                continue
        else:
            parts = [int(w or 0) for w in weights]
            if any(p < 1 for p in parts):
                res.ok = False
                res.errors.append(
                    f"{c.name}: split {sp.parent} child budget must be >= 1"
                )
                continue
            if sum(parts) != budget:
                res.ok = False
                res.errors.append(
                    writecap_split_sum_error(c.name, sp.parent, budget, sum(parts))
                )
                continue
        for name, part in zip(names, parts):
            if name in live or name in consumed or name in signal_names:
                res.ok = False
                res.errors.append(
                    f"{c.name}: split child {name} collides with a live name"
                )
                continue
            live[name] = (target, part)

    seen_borrow: set[str] = set()
    for name, sites in borrows.items():
        if len(sites) > 1 or name in seen_borrow:
            res.ok = False
            res.errors.append(writecap_reuse_error(c.name, name))
        seen_borrow.add(name)
        if name in consumed:
            res.ok = False
            res.errors.append(writecap_reuse_error(c.name, name))
            continue
        if name not in live:
            res.ok = False
            res.errors.append(writecap_unknown_error(c.name, name))
            continue
        target, budget = live.pop(name)
        consumed.add(name)
        owned = [st for owner, st in writes if owner == name]
        if len(owned) > budget:
            res.ok = False
            res.errors.append(writecap_exhausted_error(c.name, len(owned), budget))
        for st in owned:
            got = _write_target_of(st)
            if got and got != target:
                res.ok = False
                err = writecap_target_error(c.name, name, target, got)
                if err not in res.errors:
                    res.errors.append(err)

    for owner, st in writes:
        if owner is not None:
            continue
        label = _is_cap_write(st) or "write"
        err = writecap_ambient_error(c.name, label)
        if err not in res.errors:
            res.ok = False
            res.errors.append(err)


INTERVAL_COUNT_ATTRS = frozenset({"n", "e"})


def controller_stamps_predictive_freeze(c: Controller) -> bool:
    """Stamp when PredictiveFreeze is composed (fire needs N HO-scale gaps)."""
    return "PredictiveFreeze" in c.compose


def predictive_freeze_fire_line() -> str:
    """Visible check line: fire-condition honesty from LANGUAGE/EVAL."""
    return (
        f"predictive_freeze={PREDICTIVE_FREEZE_FIRE_STAMP}  "
        f"(p_ho gate; {PREDICTIVE_FREEZE_MIN_HO_GAPS} HO-scale gaps)"
    )


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


def power_low_warning(name: str, n_seeds: int) -> str:
    return (
        f"contract {name}: {n_seeds} seeds "
        f"(power=low for p-values; n<{POWER_OK_MIN_SEEDS})"
    )


def fairness_needs_multi_error(name: str) -> str:
    return (
        f"contract {name}: jain/fairness assert requires scenario {FAIRNESS_SCENARIO} "
        "(RFC 5166 holdout; not a silent README)"
    )


def _check_paths(prog: Program, res: CheckResult) -> None:
    if not prog.paths:
        return
    if "std.path" not in prog.uses:
        res.ok = False
        res.errors.append(path_needs_std_error())
    laws = parse_program_paths(prog.paths)
    for law in laws:
        for err in law.errors:
            res.ok = False
            res.errors.append(err)
        warn = house_mismatch_warning(law)
        if warn:
            res.warnings.append(warn)
        unbound = unbound_path_warning(law)
        if unbound:
            res.warnings.append(unbound)
    bound = [law for law in laws if law.bound]
    if bound:
        res.path_bound = bound[0].stamp()
    elif laws:
        res.path_bound = laws[0].stamp()
    res.path_digest = path_digest(laws)


def _check_fairness_contract(con, res: CheckResult) -> None:
    has_jain = any(assert_names_jain(a.left) for a in con.asserts)
    has_multi = FAIRNESS_SCENARIO in con.scenarios
    if has_jain and not has_multi:
        res.ok = False
        res.errors.append(fairness_needs_multi_error(con.name))
    elif has_multi and not has_jain:
        res.warnings.append(
            f"contract {con.name}: {FAIRNESS_SCENARIO} without a jain assert "
            "(fairness holdout is not scored)"
        )
    if has_jain:
        floors = [parse_jain_floor(a.right) for a in con.asserts if assert_names_jain(a.left)]
        if any(f is None for f in floors):
            res.ok = False
            res.errors.append(
                f"contract {con.name}: jain floor must be a number in (0, 1]"
            )


def _walk_oracle(cname: str, expr, res: CheckResult) -> None:
    if expr is None:
        return
    hit = oracle_name_of(expr)
    if hit:
        res.ok = False
        res.errors.append(oracle_error(cname, hit))
        return
    _walk_oracle(cname, getattr(expr, "left", None), res)
    _walk_oracle(cname, getattr(expr, "right", None), res)
    for a in getattr(expr, "args", []) or []:
        _walk_oracle(cname, a, res)


def _check_oracle_in_stmts(cname: str, stmts: list[Stmt], res: CheckResult) -> None:
    for st in _flatten_stmts(stmts):
        if st.expr is not None:
            _walk_oracle(cname, st.expr, res)
        for a in st.args:
            if hasattr(a, "kind"):
                _walk_oracle(cname, a, res)
            elif isinstance(a, tuple) and len(a) == 2:
                _walk_oracle(cname, a[1], res)


def _check_oracle(c: Controller, res: CheckResult) -> None:
    for o in c.ons:
        _check_oracle_in_stmts(c.name, o.body, res)
        for arm in o.match_arms:
            _check_oracle_in_stmts(c.name, arm.body, res)
    for w in c.whens:
        _walk_oracle(c.name, w.pred, res)
        _check_oracle_in_stmts(c.name, w.body, res)
    for e in c.everys:
        _check_oracle_in_stmts(c.name, e.body, res)
    for s in c.signals:
        if s.name in ("next_capacity", "next_capacity_bps"):
            res.ok = False
            res.errors.append(oracle_error(c.name, s.name))


def _controller_mentions_oracle(c: Controller) -> bool:
    probe = CheckResult(ok=True)
    _check_oracle(c, probe)
    return bool(probe.errors)


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
