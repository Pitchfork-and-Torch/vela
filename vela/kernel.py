"""VELA composition kernel: HorizonCCA on top of LeoAware."""
from __future__ import annotations

from collections import deque
from typing import TYPE_CHECKING, Optional

from vela.ir import VelaConfig

if TYPE_CHECKING:
    pass

MSS = 1200


def _median(xs: list[float]) -> float:
    if not xs:
        return 0.0
    s = sorted(xs)
    return s[len(s) // 2]


def make_cca(cfg: Optional[VelaConfig] = None):
    """Return a BaseCCA factory bound to this VELA config."""
    cfg = cfg or VelaConfig()

    def factory():
        return HorizonCCA(cfg)

    return factory


class HorizonCCA:
    """
    VELA kernel. Detect/reprobe stay LeoAware. Extra mechanisms are
    declared in compose and executed with epoch write budgets.
    """

    name = "Horizon"

    def __init__(self, cfg: Optional[VelaConfig] = None, **kw):
        self.cfg = cfg or VelaConfig()
        self.name = self.cfg.name or "Horizon"
        self._leo = self._make_leo(**kw)
        self._ho_gaps: deque[float] = deque(maxlen=8)
        self._last_ho_t = -1e9
        self._shield_refused = 0
        self._prev_reconfig_t = -1e9
        self.chase_until = -1.0
        self.fill_until = -1.0
        self._hold_cwnd: Optional[float] = None
        self._reclaim_left = float(self.cfg.trim_reclaim_budget_mss) * MSS
        self._fill_steps = 0
        self._last_fill_arm_t = -1e9
        self._apsis_shots = 0
        self._apsis_clean_s = 0.0
        self._last_shot_t = -1e9
        self._prev_post_t = 0.0
        self._last_p95_hint = 0.0
        self.uncertainty = 1.0
        self.bw_lo = 0.0
        self.bw_mid = 0.0
        self.bw_hi = 0.0
        self.p_ho = 0.0
        self.vela_mode = "init"

    def _make_leo(self, **kw):
        Leo = _leo_class()
        cca = Leo(**kw)
        # wrap enter_reprobe
        orig = cca._enter_reprobe

        def wrapped(t, reason, **okw):
            rtt_ref = cca.min_rtt if cca.min_rtt < 1e17 else (cca.rtt_ewma or 0.04)
            if self.cfg.quiet_shield and self._should_shield(t, cca, reason):
                self._shield_refused += 1
                return
            prev_ho = self._last_ho_t
            before_n = int(getattr(cca, "reconfigs_detected", 0) or 0)
            before_cwnd = float(cca.cwnd)
            pre_dr = self._delay_ratio_of(cca)
            orig(t, reason, **okw)
            entered = int(getattr(cca, "reconfigs_detected", 0) or 0) > before_n
            if (
                entered
                and self.cfg.soft_flicker
                and str(reason).startswith("ep:")
            ):
                rtt_hit = any(
                    tok in str(reason)
                    for tok in ("rtt_mad", "rtt_jump", "rtt_classic")
                )
                if (
                    not rtt_hit
                    and pre_dr < float(self.cfg.soft_flicker_dr)
                ):
                    # Keep the epoch invalidate. Soften only the 0.58 cut.
                    floor = before_cwnd * float(self.cfg.soft_flicker_cut)
                    if cca.cwnd < floor:
                        cca.cwnd = floor
            if entered:
                why = str(reason)
                rtt_hit = any(
                    tok in why for tok in ("rtt_mad", "rtt_jump", "rtt_classic")
                )
                dt = t - prev_ho
                if rtt_hit and (prev_ho < -1e8 or 8.0 < dt < 28.0):
                    if prev_ho > -1e8:
                        self._ho_gaps.append(dt)
                    self._last_ho_t = t
                elif rtt_hit and dt >= 28.0:
                    self._last_ho_t = t
            if self.cfg.horizon_chase:
                # Hard cap. Uncapped rtt_ref made chase last the whole run
                # (seed-7 ablation: chase-only 55 Mbps / 173 ms).
                rtt_cap = min(max(float(rtt_ref), 0.02), 0.08)
                self.chase_until = float(cca.reprobe_until) + min(
                    0.18, self.cfg.chase_rtts * rtt_cap
                )
            if self.cfg.trim_fill and entered:
                # Epoch-scale only. Detect storms (dt<6s) are not epochs.
                # Filling every REPROBE dumped seed 7 to 184 ms p95.
                if (t - self._last_fill_arm_t) > 6.0:
                    self.fill_until = float(cca.reprobe_until) + float(
                        self.cfg.trim_fill_window_s
                    )
                    self._fill_steps = 0
                    self._last_fill_arm_t = t
            self._reclaim_left = float(self.cfg.trim_reclaim_budget_mss) * MSS
            self._hold_cwnd = None
            self._apsis_shots = 0
            self._apsis_clean_s = 0.0
            self._last_shot_t = -1e9
            self.uncertainty = 1.0
            self.bw_lo = self.bw_mid = self.bw_hi = 0.0

        cca._enter_reprobe = wrapped  # type: ignore[method-assign]
        return cca

    def __getattr__(self, name: str):
        return getattr(self._leo, name)

    # ---- BaseCCA surface (explicit, not only getattr) ----
    def on_ack(self, t: float, rtt_s: float, bytes_acked: int, lost: int = 0) -> None:
        self._leo.on_ack(t, rtt_s, bytes_acked, lost)
        if t < getattr(self._leo, "freeze_until", -1.0):
            self.vela_mode = "ascent_freeze"
            return
        if t < getattr(self._leo, "reprobe_until", 0.0):
            self.vela_mode = self._leo.mode
            return
        self._vela_post(t, rtt_s, bytes_acked)

    def on_loss(self, t: float, bytes_lost: int, congestive: bool) -> None:
        self._leo.on_loss(t, bytes_lost, congestive)

    def on_path_hint(self, t: float, reconfigured: bool, **kw) -> None:
        self._leo.on_path_hint(t, reconfigured, **kw)

    def on_orb_signal(self, t: float, sig) -> None:
        self._leo.on_orb_signal(t, sig)

    def on_ecn(self, t: float, ce_count: int = 1) -> None:
        self._leo.on_ecn(t, ce_count)

    def can_send(self, t: float) -> int:
        return self._leo.can_send(t)

    def on_sent(self, n: int) -> None:
        self._leo.on_sent(n)

    def on_delivered(self, n: int) -> None:
        self._leo.on_delivered(n)

    def state(self):
        st = self._leo.state()
        if self.vela_mode and self.vela_mode not in ("init",):
            st.mode = f"vela:{self.vela_mode}"
        return st

    @property
    def cwnd(self) -> float:
        return self._leo.cwnd

    @cwnd.setter
    def cwnd(self, v: float) -> None:
        self._leo.cwnd = v

    @property
    def bytes_in_flight(self) -> int:
        return self._leo.bytes_in_flight

    @property
    def pacing_rate_bps(self) -> float:
        return self._leo.pacing_rate_bps

    @pacing_rate_bps.setter
    def pacing_rate_bps(self, v: float) -> None:
        self._leo.pacing_rate_bps = v

    # ---- VELA mechanisms ----
    def _pred_ho_t(self) -> Optional[float]:
        if len(self._ho_gaps) < 2 or self._last_ho_t < -1e8:
            return None
        med = _median(list(self._ho_gaps))
        return float(self._last_ho_t) + med

    def _should_shield(self, t: float, cca, reason) -> bool:
        """Refuse a counterfeit epoch: endpoint detect with no RTT jump.

        v1 used 8-28s gaps as trusted hops. False detects 8s apart became
        'hops' and the next real handover was suppressed (seed 7 45s:
        79.13 / 76.2 vs Leo 88.65 / 108.4). An epoch edge without an RTT
        token is the counterfeit. rtt_mad / rtt_jump / rtt_classic pass.
        """
        why = str(reason)
        if not why.startswith("ep:"):
            return False
        rtt_hit = any(
            tok in why for tok in ("rtt_mad", "rtt_jump", "rtt_classic")
        )
        if rtt_hit:
            return False
        # Dual-gate as a live object: on hard seeds the 0.58 cut is
        # p95 protection. Do not steal it.
        if self.cfg.dual_gate_guard and self._recent_p90() > float(self.cfg.slack_p90_s):
            return False
        return True

    def _update_p_ho(self, t: float, rtt_s: float) -> None:
        pred = self._pred_ho_t()
        if pred is None:
            self.p_ho = 0.0
            return
        lead = self.cfg.freeze_lead_rtts * max(rtt_s, 0.03)
        dt = pred - t
        if dt <= 0:
            # shortly after predicted hop: decay
            self.p_ho = 0.15 if dt > -0.4 else 0.0
            return
        if dt > lead * 3:
            self.p_ho = 0.05
        elif dt > lead:
            self.p_ho = 0.20
        else:
            self.p_ho = min(0.85, 0.40 + 0.45 * (1.0 - dt / max(lead, 1e-3)))

    def _interval_from_samples(self) -> None:
        samples = list(getattr(self._leo, "bw_samples", []))
        vals = sorted(b for _, b in samples) if samples else []
        if len(vals) < 3:
            self.uncertainty = 0.85 if not vals else 0.55
            if vals:
                self.bw_mid = vals[len(vals) // 2]
                self.bw_lo = vals[0]
                self.bw_hi = vals[-1]
            return
        def q(p: float) -> float:
            return vals[int(max(0, min(len(vals) - 1, p * (len(vals) - 1))))]

        self.bw_lo = q(0.35)
        self.bw_mid = q(0.70)
        self.bw_hi = q(0.90)
        mid = max(self.bw_mid, 1.0)
        self.uncertainty = max(0.08, min(1.0, (self.bw_hi - self.bw_lo) / mid))

    def _vela_post(self, t: float, rtt_s: float, bytes_acked: int) -> None:
        self._update_p_ho(t, rtt_s)
        if self.cfg.interval_bw:
            self._interval_from_samples()
        # IntervalBw is an observation. It must not silently replace
        # LeoAware's bw_est (first two evals: that plus extra yield
        # cost 10+ Mbps). Horizon v0.1.2 writes pace/cwnd only from
        # PredictiveFreeze and a gated stable-epoch reclaim.

        # House 90s (eval_horizon-house.json): pace-clamp + reclaim
        # regressed seed 123 to 57.5 Mbps / 192 ms vs LeoAware 62.7 / 111.
        # v0.1.4 shipped Horizon is observe-only. Writes stay behind
        # horizon_chase (stdlib, compose-gated) until ablation is green.
        if self.cfg.horizon_chase and t < self.chase_until:
            self._apply_chase(t, rtt_s, bytes_acked)
            return
        if (
            self.cfg.trim_hold
            or self.cfg.trim_fill
            or self.cfg.trim_reclaim
            or self.cfg.quiet_reach
        ):
            self._luff_post(t, rtt_s)
            return
        self.vela_mode = "observe"

    def _luff_post(self, t: float, rtt_s: float) -> None:
        """One cwnd write per ACK. Hold > QuietReach > Fill > Reclaim."""
        if self._prev_post_t <= 0:
            dt = 0.0
        else:
            dt = max(0.0, min(t - self._prev_post_t, 0.05))
        self._prev_post_t = t
        dr = self._delay_ratio(rtt_s)
        bdp = self._bdp(rtt_s)
        streak = int(getattr(self._leo, "high_delay_streak", 0) or 0)

        # 1. LEVEL: latch cwnd on approach. Not a multiply, not a cut.
        if self.cfg.trim_hold and self.p_ho > float(self.cfg.trim_hold_p_ho):
            if self._hold_cwnd is None:
                self._hold_cwnd = float(self._leo.cwnd)
            else:
                self._leo.cwnd = min(float(self._leo.cwnd), self._hold_cwnd)
            self._apsis_clean_s = 0.0
            self.vela_mode = "reach_hold"
            return
        self._hold_cwnd = None

        if (
            dr >= float(self.cfg.quiet_reach_dr)
            or streak > 0
            or self.p_ho > float(self.cfg.quiet_reach_p_ho)
        ):
            self._apsis_clean_s = 0.0
        else:
            self._apsis_clean_s += dt

        # 2. APOAPSIS: confirmed-quiet level-set toward this epoch's bw.lo.
        #    Not prior_bdp. Not post-hop jumped RTT. At most N shots / epoch.
        if self.cfg.quiet_reach:
            if self._try_quiet_reach(t, rtt_s, dr, streak):
                return

        # 3. Legacy Luff fill (stdlib). Not in Reach compose.
        if (
            self.cfg.trim_fill
            and t < self.fill_until
            and self._fill_steps < int(self.cfg.trim_fill_steps)
        ):
            prior = float(getattr(self._leo, "prior_bdp", 0.0) or 0.0)
            if prior > 0 and dr < 1.30:
                floor = prior * float(self.cfg.trim_fill_frac)
                if self._leo.cwnd < floor:
                    self._leo.cwnd += MSS * 0.10
                    self._fill_steps += 1
                    self.vela_mode = "luff_fill"
                    return

        # 4. Legacy reclaim. Seed-7 45s with it: 83.8 / 184.9. Off compose.
        if (
            self.cfg.trim_reclaim
            and self._reclaim_left > 0
            and bdp > 0
        ):
            age = t - float(self._leo.last_reconfig_t)
            mode = str(getattr(self._leo, "mode", ""))
            if (
                age > 4.0
                and self.p_ho < 0.12
                and self.uncertainty < 0.20
                and 1.45 < dr < 1.52
                and streak < 3
                and "delay_yield" in mode
            ):
                step = MSS * 0.30
                self._leo.cwnd += step
                self._reclaim_left -= step
                self.vela_mode = "luff_reclaim"
                return

        self.vela_mode = "reach_cruise"

    def _recent_p90(self) -> float:
        hist = list(getattr(self._leo, "rtt_hist", []))
        if len(hist) < 8:
            return 1.0
        s = sorted(hist[-16:])
        return float(s[int(0.90 * (len(s) - 1))])

    def _quiet_target(self) -> float:
        # This epoch's bw_est (Leo already 0.82-quantile) and this
        # epoch's min_rtt. Never prior_bdp, never jumped sizing RTT.
        # 1.28x is the cruise envelope above Leo's 1.15x on a clean path.
        mr = self._leo.min_rtt
        bw = float(getattr(self._leo, "bw_est", 0.0) or 0.0)
        if mr >= 1e17 or mr <= 0 or bw <= 0:
            return 0.0
        return float(self.cfg.quiet_reach_frac) * bw * mr / 8.0

    def _try_quiet_reach(
        self, t: float, rtt_s: float, dr: float, streak: int
    ) -> bool:
        if self._apsis_shots >= int(self.cfg.quiet_reach_shots):
            self.vela_mode = "reach_done"
            return False
        age = t - float(self._leo.last_reconfig_t)
        if age < float(self.cfg.quiet_reach_age_s):
            self.vela_mode = "reach_wait"
            return False
        if self._apsis_clean_s < float(self.cfg.quiet_reach_clean_s):
            self.vela_mode = "reach_wait"
            return False
        if self._apsis_shots > 0 and (t - self._last_shot_t) < float(
            self.cfg.quiet_reach_shot_gap_s
        ):
            self.vela_mode = "reach_wait"
            return False
        samples = list(getattr(self._leo, "bw_samples", []))
        # LEO intervals are supposed to be wide. Tight-uncertainty was a
        # terrestrial prior and kept QuietReach from ever firing.
        if len(samples) < 8 or self.uncertainty > float(self.cfg.quiet_reach_max_uncert):
            self.vela_mode = "reach_wait"
            return False
        if dr >= float(self.cfg.quiet_reach_dr) or streak > 0:
            self.vela_mode = "reach_wait"
            return False
        # Dual-gate as a live object: refuse aggression when p95 slack is gone.
        if self.cfg.dual_gate_guard and self._recent_p90() > float(self.cfg.slack_p90_s):
            self.vela_mode = "reach_slack"
            return False
        target = self._quiet_target()
        if target <= 0:
            self.vela_mode = "reach_wait"
            return False
        cwnd = float(self._leo.cwnd)
        if cwnd >= target * 0.92:
            self.vela_mode = "reach_cruise"
            return False
        cap = min(
            cwnd * float(self.cfg.quiet_reach_max_mult),
            cwnd + float(self.cfg.quiet_reach_max_mss) * MSS,
        )
        new = min(target, cap)
        if new <= cwnd + 0.25 * MSS:
            self.vela_mode = "reach_cruise"
            return False
        self._leo.cwnd = new
        self._apsis_shots += 1
        self._last_shot_t = t
        self.vela_mode = "reach_apsis"
        return True

    def _stable_reclaim(self, t: float, rtt_s: float) -> None:
        """Tiny fill only in a long, tight, low-p_ho epoch (v3.4 left gp on the table)."""
        age = t - float(self._leo.last_reconfig_t)
        if age < 2.8 or self.p_ho > 0.15:
            return
        dr = self._delay_ratio(rtt_s)
        bdp = self._bdp(rtt_s)
        if bdp <= 0 or dr > 1.22 or self.uncertainty > 0.28:
            return
        if self._leo.cwnd < bdp * 1.16:
            self._leo.cwnd += MSS * 0.18
            self.vela_mode = "reclaim"

    def _bdp(self, rtt_s: float) -> float:
        bw = float(self._leo.bw_est or 0.0)
        mr = self._leo.min_rtt if self._leo.min_rtt < 1e17 else rtt_s
        if bw <= 0 or mr <= 0:
            return 0.0
        hist = list(getattr(self._leo, "rtt_hist", []))
        sizing = mr
        if len(hist) >= 8:
            med = _median(hist[-8:])
            if med > 1.25 * mr:
                sizing = 0.50 * mr + 0.50 * med
            else:
                sizing = 0.72 * mr + 0.28 * med
        return bw * sizing / 8.0

    def _delay_ratio(self, rtt_s: float) -> float:
        mr = self._leo.min_rtt if self._leo.min_rtt < 1e17 else rtt_s
        hist = list(getattr(self._leo, "rtt_hist", []))
        floor = mr
        if len(hist) >= 12:
            floor = max(min(hist[-12:]), mr * 0.85)
        return rtt_s / max(floor, 1e-4)

    def _delay_ratio_of(self, cca) -> float:
        hist = list(getattr(cca, "rtt_hist", []))
        mr = getattr(cca, "min_rtt", 1e18)
        if not hist:
            return 1.0
        rtt_s = float(hist[-1])
        if mr >= 1e17 or mr <= 0:
            return 1.0
        floor = mr
        if len(hist) >= 12:
            floor = max(min(hist[-12:]), mr * 0.85)
        return rtt_s / max(floor, 1e-4)

    def _apply_chase(self, t: float, rtt_s: float, bytes_acked: int) -> None:
        dr = self._delay_ratio(rtt_s)
        bdp = self._bdp(rtt_s)
        self.vela_mode = "chase"
        if dr > 1.35 or bdp <= 0:
            self.chase_until = t
            self.vela_mode = "chase_abort"
            return
        # Cap against prior_bdp. Fresh post-hop BDP using a jumped RTT
        # is huge and "underfill" becomes a 180ms cwnd flood (seed 7).
        prior = float(getattr(self._leo, "prior_bdp", 0.0) or 20 * MSS)
        target = min(0.88 * bdp, prior * 1.02)
        if self._leo.cwnd < target:
            self._leo.cwnd += MSS * 0.10
            self.vela_mode = "chase_fill"

    def _uncertainty_yield(self, t: float, rtt_s: float) -> None:
        dr = self._delay_ratio(rtt_s)
        bdp = self._bdp(rtt_s)
        if bdp <= 0:
            return
        u = self.uncertainty
        # high u or high p_ho: yield early (protect p95)
        # low u stable epoch: allow closer to 1.15x BDP (reclaim goodput)
        # Extra yield only when both uncertainty and delay are high.
        # Clean-epoch reclaim is a small additive step on top of v3.4.
        if dr > 1.62 and u > 0.50:
            self._leo.cwnd = max(4 * MSS, self._leo.cwnd * 0.98)
            self.vela_mode = "u_yield"
        elif u < 0.25 and dr < 1.26 and self.p_ho < 0.20 and self._leo.cwnd < bdp * 1.16:
            self._leo.cwnd += MSS * 0.22
            self.vela_mode = "reclaim"

    def _gate_ease(self, rtt_s: float) -> None:
        # Live guard: if delay is already in the p95 danger zone, kill chase leftover.
        dr = self._delay_ratio(rtt_s)
        if dr > 1.70 and self.chase_until > 0:
            self.chase_until = 0.0


_LEO_CLS = None


def _leo_class():
    global _LEO_CLS
    if _LEO_CLS is not None:
        return _LEO_CLS
    import sys
    from pathlib import Path

    root = Path.home() / "Projects" / "leo-aware-transport"
    if str(root) not in sys.path:
        sys.path.insert(0, str(root))
    from leo_cc.ccas import LeoAwareCCA

    _LEO_CLS = LeoAwareCCA
    return _LEO_CLS


def oce_cca_factory():
    """Reconstructed OCE-class: LeoAware + post-reprobe point chase (no interval)."""
    cfg = VelaConfig(
        name="LeoAwareOCE",
        mechanisms=["Detect", "SoftReprobe", "OCE"],
        predictive_freeze=False,
        interval_bw=False,
        horizon_chase=True,
        typed_loss=True,
        dual_gate_guard=False,
        oce_legacy=True,
        chase_rtts=3.0,
        chase_bdp_div=1.42,
        rollback_delay=1.42,
        freeze_lead_rtts=0.0,
    )
    return make_cca(cfg)
