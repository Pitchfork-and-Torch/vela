# Cursor swarm roles (space internet)

Read `docs/MISSION.md` and `lab/WORKDAY.md` first.

VELA builds onto LeoAware. Do not fork Detect/SoftReprobe. Do not enable HorizonChase, TrimFill, TrimReclaim, QuietReach, QuietShield, SoftFlicker, or TrimHold.

## Measurer

Run isolated evals from `lab/BACKLOG.json` items with kind=eval.

```
py -3 scripts/space_internet_loop.py --once
```

Write results to `lab/journal.jsonl`. If seed 7 45s moves more than 0.05 Mbps / 0.2 ms from 88.65 / 108.4, revert and mark fail.

## Language

Implement one LANGUAGE.md gap per session. Closed-write compose still needs `posture review`. Observe `when`/`every` cannot write pace/cwnd. Observe Loss is type-directed (Mobility holds; Unknown needs delay_ratio). Public README teaser is Reach (observe-only, passthrough), not a cruise-write Horizon. Tests must stay green (`py -3 -m unittest discover -s tests -q`). No packet-path writes.

## Publisher

```
py -3 scripts/space_internet_loop.py --publish --dry-run
py -3 scripts/space_internet_loop.py --publish
```

`--publish` must go through the progress sanitizer. Never naive-copy `lab/PUBLIC_PROGRESS.json` onto a public site. Never copy ablation dumps, kernel source, or failed-operator names.

## Stop

If `lab/STOP` exists, write a recap into `lab/STATE.md` and exit.
