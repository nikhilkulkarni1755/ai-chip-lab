# COORDINATION — AI-chip-lab agent team

Single source of truth for all agents. Read it fully before acting, re-read the **Board** and **Decisions**
sections at the start of every loop iteration. The full task spec is `coord/TASK.md`.

## Machine (measured, see env.json)

- Intel i7-7660U, **2 physical / 4 logical cores, 8 GB RAM**, macOS 13.7.8, 92 GB free. No sudo, **no Homebrew (never use or suggest it)**.
- Route A (Colima + vz). VM plan: 3 CPUs, 4 GB RAM. `NUM_CORES=3`.
- This machine is the bottleneck, not the number of agents. Do not run two heavy jobs at once.

## Budget (budget.json is authoritative; owner capped the run at 6 h)

| Milestone | When |
|---|---|
| Start | 02:48 PDT |
| Baselines (stages 00–30) target | T+2h30 = 05:18 |
| Sweeps must stop | T+5h = 07:48 |
| Demo built, final STATUS = DONE | T+6h = 08:48 |

If a stage is late, cut scope (documented), never the demo.

## Rules

1. **Everything lives in `~/ai-chip-lab/`.** Always `source ~/ai-chip-lab/env.sh` first (PATH, DOCKER_CONFIG, COLIMA_HOME, LIMA_HOME are redirected into the lab). Never touch shell profiles or system settings.
2. **Git.** Repo = `~/ai-chip-lab` (branch `main`, remote `origin` on GitHub, private). Work in your own worktree:
   `git -C ~/ai-chip-lab worktree add ~/ai-chip-lab/.worktrees/<agent> -b <agent>/<topic>`.
   **Atomic commits** (one logical change each, message `<area>: <what>`), ending with the trailer
   `Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>`.
   Ship the smallest working piece: rebase on `main`, then `git -C ~/ai-chip-lab merge --ff-only <branch>` and `git push origin main`. If ff fails, rebase and retry — never force-push, never rewrite `main`.
   Only touch files in your own area (see Board). Shared files (`Makefile`, `versions.lock`, `env.sh`) are append-by-section; keep edits minimal and rebase often.
3. **Runs execute from the main checkout** (`~/ai-chip-lab`), after merge. Outputs go to `results/`, `logs/<stage>/`, `demo/assets/` in the main checkout. Small result files (csv/json/png, < 5 MB) get committed; big binaries (GDS, VCD, ODB) are gitignored.
4. **Heavy jobs take the lock:** `scripts/with_lock.sh <agent> <cmd...>` for image builds/pulls and every ORFS run. Simulations and SCALE-Sim runs are light and may run unlocked, but use at most 2 threads.
5. **Status.** Never hand-edit `STATUS.md`. Write markers in `results/.stages/`: `<stage>.running`, `<stage>.done`, `<stage>.failed`, `<stage>.blocked` (file body = error + diagnosis + exact command for the owner). Remove `.running` when finished. A background heartbeat regenerates STATUS.md every minute. Append one-line events to `logs/run.log`.
6. **Ralph loop per task:** research (resolve real versions/APIs from the source, not from memory) → implement smallest piece → run → verify → commit/merge → next. **Verification is always the last step** and must be an actual executed check with output you read. Fail soft: 2 retries, then write `.failed` with the last 50 log lines and a diagnosis, and move on.
7. **NO STUB DATA.** Never fabricate, hardcode, or placeholder a result, metric, version, or digest. Every number in results/ and demo/ comes from a tool run in this lab. Missing = reported as missing/BLOCKED.
8. **Never block on a prompt.** Non-interactive flags everywhere, `timeout` (use `gtimeout` if present, else `perl -e 'alarm shift; exec @ARGV' <secs> cmd`, or a background-pid watchdog) on every long command.
9. **Resumable.** `.done` markers; sweeps append JSONL keyed by parameters and skip existing keys.
10. **Pin and record** versions, git SHAs, image digests, URLs + SHA256 in `versions.lock` (YAML-ish, your own section).
11. **Decisions.** If a decision is not contingent on the owner: find evidence from a reputable source, record it in **Decisions** below (decision, evidence/URL, date/time), and continue. If it genuinely needs the owner (credentials, sudo, spending money, anything outside the lab dir): add it to **Needs owner** below, report it in your final message to the main agent, and keep working on everything that does not depend on it.
12. **Requests between agents** go in **Requests** below (who → who, what, status). Check it every iteration.
13. When your queue is empty: re-verify your deliverables, check Requests, then report. The main agent keeps you resumable and will message you with new work — answer with the same context.
14. **The repo will be made PUBLIC at the end of the run (owner's instruction, 02:58).** Nothing private may be committed: no absolute home paths (`/Users/<name>` → write `~`, `$HOME` or `$LAB`), no hostname, no email addresses, no tokens/credentials, no raw logs that contain any of those (scrub with `sed "s#$HOME#~#g"` before committing; `logs/` stays gitignored). A pre-commit hook rejects such content — fix the content, never use `--no-verify`. Commit identity is already set repo-wide to the GitHub noreply address; do not change it. This also applies to everything under `results/`, `versions.lock`, and `demo/` (generated HTML/README/PNG must show `~`, never the real home path or username).
15. **Evidence screenshots.** The owner wants screenshots proving each thing builds and runs, for the README. Each agent, when a stage passes, saves the scrubbed, real terminal output of its key verification command(s) (the final PASS table / tool summary, ≤ 60 lines, home path replaced by `~`) to `results/evidence/<stage>_<what>.txt`. The demo agent renders these to PNG. Never fabricate or hand-edit the content beyond the path scrub and trimming.

## Board

| Agent | Owns (paths) | Stages | Depends on | State |
|---|---|---|---|---|
| main | coord/, scripts/status.sh, COORDINATION.md structure, HITL | 00_preflight | – | preflight done |
| infra | bin/, opt/, docker/, env.sh, versions.lock (runtime+images), Makefile skeleton | 01_runtime, 02_images | – | **01_runtime DONE 02:57** — docker works (`source env.sh`; DOCKER_HOST set there). Images: pulling ORFS next, then lab-sim |
| rtl | rtl/, tb/, formal/, eqy/, scripts/t1_* | 10_rtl_verify | lab-sim image (for official run) | starting (authoring) |
| arch | model/, arch/, sweeps/arch_*, scripts/t3_* | 30_arch_model, 40_sweeps A | lab-sim image (for official run) | starting (authoring) |
| pnr | orfs/, sweeps/phys_*, scripts/t2_* | 20_pnr_ref, 40_sweeps B | ORFS image; rtl (for stretch) | starting (authoring) |
| demo | demo/, scripts/repro*, | 50_repro, 60_demo | all results | not started (spawned when first results land) |

Agents update their own row's State cell (short).

## Interfaces (contracts between agents)

- Images: `lab-sim:latest` (local build, also tagged by date) and ORFS image pinned by digest; exact refs are written by infra to `coord/images.env` as `LAB_SIM_IMAGE=...` and `ORFS_IMAGE=...@sha256:...`. Scripts source that file.
- Containers mount the lab at `/lab` (`-v $LAB:/lab -w /lab`), run with `--platform linux/amd64`.
- Task summaries: `results/t1_summary.json`, `results/t2_summary.json`, `results/t3_summary.json`, `results/repro_report.json`, each with a top-level `"pass": true|false` and per-check booleans + the measured values.
- Makefile targets: `preflight runtime images t1 t2 t3 sweeps repro demo all`; each agent adds its own target calling `scripts/<its script>`.

## Decisions

| # | Time | Agent | Decision | Evidence |
|---|---|---|---|---|
| 1 | 02:48 | main | Total budget 6 h, not 14 h | Owner's wrapper instruction ("next 6 hours") supersedes task text |
| 2 | 02:48 | main | Route A (Colima vz), VM 3 CPU / 4 GB | macOS 13.7.8 ≥ 13; task §1 sizing rule (half of 8 GB, ncpu−1) |
| 3 | 02:48 | main | Lima/Colima/Docker state redirected into the lab via LIMA_HOME / COLIMA_HOME / DOCKER_CONFIG | Task rule "stay inside ~/ai-chip-lab" |
| 4 | 02:48 | main | Private GitHub repo `ai-chip-lab` as `origin` | Owner asked for gh CLI + atomic commits; private = no publication |
| 5 | 02:58 | main | Repo goes public at the END of the run, after a history scrub (first commits carry a local-hostname author address and home paths) and a full audit; private until then | Owner approved public at 02:58 with the condition that no private info is in the repo; flipping after a single final audit is the only way to guarantee that while 4 agents are still pushing |

## Needs owner

_(none yet)_

## Requests

| From → To | What | Status |
|---|---|---|
| rtl → infra | lab-sim image needs `make`, `g++` (Verilator compiles its model with the host C++ compiler; cocotb Makefile flow) and `git`; please state the pinned cocotb / cocotb-coverage versions here (I am writing to cocotb 2.x + cocotb-coverage 2.0, latest on PyPI = 2.1.0 / 2.0) | open |
| pnr → infra | **ORFS image tag: please pull `openroad/orfs:26Q3-600-g3a964e13f` (digest `sha256:573c1716efa0e286c4f641c26d343e20929d58d27fffbb22be2d0b93f09764f6`, ~1.6 GB), NOT `latest`.** Reason: ORFS removed `rules-base.json`/`checkMetadata.py` (the shipped thresholds) on 2026-09-22 (commit 76be2a8e); every 26Q4-* tag incl. `latest` lacks them (checker now needs an online dashboard). 26Q3-600 is the newest tag still shipping them. Write it as `ORFS_IMAGE=openroad/orfs@sha256:573c...64f6` in coord/images.env. | open |
