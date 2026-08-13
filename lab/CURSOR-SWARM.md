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

Implement one LANGUAGE.md gap per session: Interval n>=2 type error, `compose cuts = min`, harness INCOMPLETE. Tests must stay green (`py -3 -m unittest discover -s tests -q`). No packet-path writes.

## Publisher

Copy `lab/PUBLIC_PROGRESS.json` to `orbitstack/public/progress.json`. Never copy ablation dumps, kernel source, or failed-operator names. Deploy orbitstack only after the JSON is sanitized.

## Stop

If `lab/STOP` exists, write a recap into `lab/STATE.md` and exit.
