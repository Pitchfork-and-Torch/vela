# Cursor swarm roles (space internet)

Read `docs/MISSION.md` and `lab/WORKDAY.md` first. Free-first. No Task Scheduler. No reboot.

VELA builds onto LeoAware. Do not fork Detect/SoftReprobe. Do not enable HorizonChase, TrimFill, TrimReclaim, QuietReach, QuietShield, SoftFlicker, or TrimHold.

## Measurer

Run isolated evals from `lab/BACKLOG.json` items with kind=eval.

```
py -3 scripts/space_internet_loop.py --once
```

Write results to `lab/journal.jsonl`. If seed 7 45s moves more than 0.05 Mbps / 0.2 ms from 88.65 / 108.4, revert and mark fail.

## Language

Implement one LANGUAGE.md gap per session. Interval n>=2, compose cuts/growth, harness INCOMPLETE, observe posture, hint law, typed reconfig, passthrough, typed loss, and teaser safety already landed (PRs 4/5/6/7/8/9/10/11 plus teaser). Closed-write compose still needs `posture review`. Observe `when`/`every` cannot write pace/cwnd. Observe Loss is type-directed (Mobility holds; Unknown needs delay_ratio). Public README teaser is Reach (observe-only, passthrough), not a cruise-write Horizon. Tests must stay green (`py -3 -m unittest discover -s tests -q`). No packet-path writes.

## Publisher

```
py -3 scripts/space_internet_loop.py --publish --dry-run
py -3 scripts/space_internet_loop.py --publish
```

Desk-check dry-run first. That must call `~/orbitstack/scripts/publish_progress.py`. Never naive-copy `lab/PUBLIC_PROGRESS.json` onto `orbitstack/public/progress.json` (lab file is coupled-era and would clobber Current Crest). Never copy ablation dumps, kernel source, or failed-operator names. Deploy orbitstack only after the sanitizer exits 0.

## Stop

If `lab/STOP` exists, write a recap into `lab/STATE.md` and exit.
