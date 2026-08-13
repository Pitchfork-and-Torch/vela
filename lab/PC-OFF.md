# PC-off workday (2026-08-14)

The Windows box will be off. Local Start-SpaceInternetLoop.ps1 will not run.
No Task Scheduler (PC-AUTOMATION-HOLD).

## Who works

| Worker | Host | Job |
|--------|------|-----|
| Cursor Cloud Agents | cursor.com VMs | Language PRs on private `Pitchfork-and-Torch/vela` |
| Cursor Automations | schedule / Linear / GitHub issue | Same, if you save the automation at cursor.com/automations |
| KnockNGrok | Hetzner VPS | Morning + midday Telegram kick with issue links |
| Public engine | GitHub clone on VPS (optional) | LeoAware sim only. No VELA compiler on the VPS. |

## Linear (due 2026-08-14)

- JON-11 Interval n>=2
- JON-12 compose cuts/growth
- JON-13 harness INCOMPLETE
- JON-14 public-safe measurer note

## GitHub (private vela)

- https://github.com/Pitchfork-and-Torch/vela/issues/1
- https://github.com/Pitchfork-and-Torch/vela/issues/2
- https://github.com/Pitchfork-and-Torch/vela/issues/3

## Grok cloud tasks (already created)

Weekday email/app briefs. PC not required.

- Space internet morning cook - 09:20 ET
- Space internet midday cook - 13:15 ET
- Space internet EOD cook - 17:35 ET

## GitHub Actions (private vela)

`space-internet-workday` at 09:20 and 13:20 ET weekdays: unit tests + public LeoAware import smoke.

## Cursor Cloud Agents (launched 2026-08-13, Grok 4.6 high)

No click required. Key stayed on Desktop `cursorapiforyou.txt` (not in git).

| Job | Agent | Branch |
|-----|-------|--------|
| JON-11 Interval n>=2 | https://cursor.com/agents/bc-9ef8152a-be9a-4c39-a1f1-b7bf133f33c7 | `cursor/vela-jon-11-interval-n-2-ac6b` |
| JON-12 compose cuts/growth | https://cursor.com/agents/bc-5d32af3a-d35b-4f51-8cd9-c683d0ca385d | `cursor/vela-jon-12-compose-cuts-growth-e650` |
| JON-13 harness INCOMPLETE | https://cursor.com/agents/bc-bc264b33-d1a5-4e67-8de3-8fbd0623f64a | `cursor/vela-jon-13-harness-incomplete-d2ce` |

IDs also in `lab/cursor-agents.json`. Relight: `py -3 scripts/launch_cursor_cloud.py` (same Desktop key file).

## Operator phone

1. Watch https://cursor.com/agents (three VELA jobs already running)
2. Review PRs when they open. Do not merge write-enabled CCA composes
3. Watch Telegram @KnockNGrok_bot for VPS kicks
4. Optional: save a Cursor Automation at cursor.com/automations if you want a weekday cron (no REST create as of 2026-08-13)

## Secrets

Do not copy the VELA kernel or ablation JSON to the VPS.
Public site progress stays means-only.
