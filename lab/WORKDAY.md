# Workday cook (manual start)

**Objective:** Improve space internet on top of LeoAware without regressing the engine.

**State:** `lab/STATE.md`, `lab/journal.jsonl`, `lab/PUBLIC_PROGRESS.json`

**Act:** `scripts/space_internet_loop.py --once` from the backlog. Isolated evals only.

**Validate:** seed 7 45s must stay within 0.05 Mbps / 0.2 ms of LeoAware 88.65 / 108.4. Then seed 123 90s. Then terrestrial >= 77 @ 40.

**Stop:** `lab/STOP` exists, or work-hours end, or backlog empty.

**Anti-hack:** do not edit LeoAware to make a VELA wrap look good. Do not enable closed-write operators. Do not claim dish Mbps.

## Start

```
powershell -ExecutionPolicy Bypass -File .\scripts\Start-SpaceInternetLoop.ps1 -Hours 9
```

Optional: `-Publish` runs `space_internet_loop.py --publish` (progress sanitizer) and deploys the public progress site only if the sanitizer exits 0. Never naive-copy the lab JSON.

## Cursor swarm

Give each agent `lab/CURSOR-SWARM.md` plus one role: Measurer, Language, Publisher.
