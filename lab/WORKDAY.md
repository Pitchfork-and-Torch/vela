# Workday cook (manual start)

**Objective:** Improve space internet on top of LeoAware without regressing the engine.

**State:** `lab/STATE.md`, `lab/journal.jsonl`, `lab/PUBLIC_PROGRESS.json`

**Act:** `scripts/space_internet_loop.py --once` from the backlog. Isolated evals only.

**Validate:** seed 7 45s must stay within 0.05 Mbps / 0.2 ms of LeoAware 88.65 / 108.4. Then seed 123 90s. Then terrestrial >= 77 @ 40.

**Stop:** `lab/STOP` exists, or work-hours end, or backlog empty.

**Budget:** one workday. Free-first. No paid spawn storms.

**Anti-hack:** do not edit LeoAware to make a VELA wrap look good. Do not enable closed-write operators. Do not claim dish Mbps.

## Start (operator, before work)

```
powershell -ExecutionPolicy Bypass -File $env:USERPROFILE\vela\scripts\Start-SpaceInternetLoop.ps1 -Hours 9
```

Optional: `-Publish` runs `space_internet_loop.py --publish` (orbitstack `publish_progress.py` sanitizer) and deploys that site only if the sanitizer exits 0. Never naive-copy the lab JSON.

If the PC is **off**, do not start this script. Use `lab/PC-OFF.md` (Cursor Cloud + KnockNGrok VPS kicks).
If the PC is on: stays ON + LOCKED + AC. Do not create Task Scheduler jobs.

## Cursor swarm

Open the `vela` folder and `Projects/leo-aware-transport` in Cursor. Give each agent `lab/CURSOR-SWARM.md` plus one role: Measurer, Language, Publisher.
