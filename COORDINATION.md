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
| infra | bin/, opt/, docker/, env.sh, versions.lock (runtime+images), Makefile skeleton | 01_runtime, 02_images | – | **01_runtime DONE 02:55, 02_images DONE 03:22** — `source coord/images.env`; lab-sim rebuilt as `20261012b` 03:38 (numpy 2.3.5); smoke 56/56 PASS (`results/evidence/02_images_smoke.txt`). Timeloop skipped (Decision 11). Idle: watching Requests |
| rtl | rtl/, tb/, formal/, eqy/, scripts/t1_* | 10_rtl_verify | lab-sim image (for official run) | **RTL merged to main (pnr can start):** `rtl/mac_int8.sv` + `rtl/systolic_os.sv`, top `systolic_os` (params R=4,C=4), single clock `clk`, sync `clear` (no async reset), ports `in_valid, a_i[R*8], b_i[C*8], busy, acc_o[R*C*32]` (580 port bits → wrap/serialize in orfs if pins are a problem); Yosys `synth;abc;opt` ≈ 14.5k generic cells, 815 flops. Native Icarus+Verilator sims pass (identical CSV); authoring formal/EQY/run script |
| arch | model/, arch/, sweeps/arch_*, scripts/t3_* | 30_arch_model, 40_sweeps A | lab-sim image (for official run) | wrapper+analytic fit working (exact fit); official container run + sweep A driver in progress |
| pnr | orfs/, sweeps/phys_*, scripts/t2_* | 20_pnr_ref, 40_sweeps B | ORFS image; rtl (for stretch) | starting (authoring) |
| demo | demo/, scripts/repro*, | 50_repro, 60_demo | all results | not started (spawned when first results land) |

Agents update their own row's State cell (short).

## Interfaces (contracts between agents)

- Images: `lab-sim:latest` (local build, also tagged by date) and ORFS image pinned by digest; exact refs are written by infra to `coord/images.env` as `LAB_SIM_IMAGE=...` and `ORFS_IMAGE=...@sha256:...`. Scripts source that file.
- Containers mount the lab at `/lab` (`-v $LAB:/lab -w /lab`), run with `--platform linux/amd64`.
- **ORFS image (infra, pulled + verified):** `source coord/images.env` → `$ORFS_IMAGE` = `openroad/orfs@sha256:573c1716…64f6` (tag 26Q3-600-g3a964e13f). Inside: ORFS root `/OpenROAD-flow-scripts` (default workdir, runs as root, `nproc`=3), flow at `/OpenROAD-flow-scripts/flow` (Makefile, `designs/{nangate45,sky130hd}/gcd/{config.mk,rules-base.json}`, `util/checkMetadata.py`, `util/checkQorMetrics.py`; there is no `util/genMetadata.py` at this commit). Tools: `openroad` at `/OpenROAD-flow-scripts/tools/install/OpenROAD/bin` and yosys 0.68+post at `tools/install/yosys/bin` (run `. /OpenROAD-flow-scripts/env.sh` to put them on PATH), **KLayout 0.30.12 at `/usr/bin/klayout`**, Python 3.10.12, GNU Make 4.3. `openroad -version` prints `unknown` in this build (identify it by the image digest / ORFS commit); OpenSTA is embedded (`sta::version` = 3.1.0), there is no standalone `sta`. No KLayout in lab-sim — render GDS with the ORFS image.
- **lab-sim image (infra, built + smoke-tested):** `$LAB_SIM_IMAGE` (**`lab-sim:20261012b`** since 03:38, also `lab-sim:latest`; always read it from `coord/images.env`). Ubuntu 22.04, OSS CAD Suite 2026-09-28 in `/opt/oss-cad-suite`, Verible in `/opt/verible`, Python 3.12 venv `/opt/venv` (first on PATH: `python3`, `pytest`, `cocotb-config`), `make`, `g++`, `git`. `HOME=/tmp`, `MPLBACKEND=Agg`, `PYTHONHASHSEED=0`, thread env vars = 2. Host helpers from `env.sh`: `lab_timeout <secs> cmd…`, `DOCKER_HOST` is exported (no docker context needed).
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
| 6 | 02:58 | infra | ORFS image = `openroad/orfs:26Q3-600-g3a964e13f`, pinned as `openroad/orfs@sha256:573c1716efa0e286c4f641c26d343e20929d58d27fffbb22be2d0b93f09764f6` (index digest; linux/amd64 manifest `sha256:7fbb16f7…6deee9`), not `latest` | pnr request, verified independently: `docker buildx imagetools inspect` returns that digest for the tag; raw.githubusercontent.com has `flow/designs/nangate45/gcd/rules-base.json` and `flow/util/checkMetadata.py` at 3a964e13f (HTTP 200) and not on master (404); ORFS commit 76be2a8e (2026-09-22) "feat(metadata)!: remove the rules-file QoR check". Task 2 needs the shipped thresholds, so "newest stable" is bounded by that commit. 26Q3-605-g2d29bdaf8 (pushed 09-22) also still has them and is 5 commits newer; 600 kept because pnr authored against it |
| 7 | 02:58 | infra | VM data disk 60 GiB (sparse), root disk 20 GiB; only `$LAB` is mounted into the VM (writable, virtiofs), not `$HOME` | 92 GB free at start: a full 60 GiB disk still leaves ~30 GB host headroom; ORFS 1.6 GB + lab-sim compressed sizes are far below it |
| 8 | 02:58 | infra | `env.sh` creates `$COLIMA_HOME` before use and exports `DOCKER_HOST`; Colima started with `--ssh-config=false --activate=false` and `XDG_CACHE_HOME=$LAB/.cache` | Tested: Colima 0.10.3 silently falls back to `~/.colima` when `COLIMA_HOME` does not exist yet; the flags keep it from writing `~/.ssh/config` / a docker context; verified nothing was created under `~/.colima`, `~/.lima`, `~/.docker`, `~/Library/Caches/{lima,colima}`. Socket paths are 62–75 chars, under the 104-char UNIX limit, so no shorter path was needed |
| 9 | 02:58 | infra | buildx v0.38.0 darwin binary verified by GitHub release-API asset digest + Docker Inc Developer ID code signature | The release's `checksums.txt` has no darwin/windows entries (binaries are signed after the checksummed build), so the usual check is impossible; Docker CLI static tgz has no published checksum at all (SHA256 computed locally and recorded) |
| 10 | 03:11 | infra | lab-sim ships `/opt/lab-bin/{vvp,iverilog}` ahead of the OSS CAD Suite on PATH; Python deps are hash-locked with `uv pip compile --exclude-newer 2026-09-28` (cocotb 2.1.0, cocotb-coverage 2.0, numpy 2.5.3 (superseded: 2.3.5, see Decision 12), pandas 3.0.6, matplotlib 3.11.2, scalesim 3.0.0 from PyPI, numba 0.67.0, Python 3.12.15); OSS CAD Suite pinned to 2026-09-28 (two weeks old rather than the build published hours before the run); no KLayout in lab-sim | Tested in the container: the suite's `bin/vvp` wrapper exports `PYTHONHOME`/`PYTHONEXECUTABLE` for its private Python 3.11, so cocotb's embedded 3.12 interpreter died with "failed to get the Python codec of the filesystem encoding"; cocotb finds vvp next to `which iverilog`, hence both shims. After the fix both simulators pass the self-test. numpy ≥2.5 needs Python ≥3.12 and cocotb-coverage 2.0 needs ≥3.11 (PyPI metadata), Ubuntu 22.04 has 3.10 → uv-managed CPython. KLayout 0.30.12 is already in the ORFS image |
| 11 | 03:22 | infra | Timeloop/Accelergy image SKIPPED (optional per TASK.md §3/§6) | Not a disk problem (66 GB host / 41 GB VM free) but a time one: the 6 h budget is dominated by the single heavy-job lock (ORFS baselines + sweep B), no agent has requested it, and Task 3 pass criteria do not depend on it. To add later: `scripts/with_lock.sh infra docker pull --platform linux/amd64 timeloopaccelergy/accelergy-timeloop-infrastructure:latest-amd64` (Docker Hub lists it at 1.25 GB compressed, last pushed 2025-10-07), then pin by the digest the pull prints |
| 12 | 03:38 | infra | lab-sim re-locked to numpy 2.3.5 + numba 0.62.1 and rebuilt as a new tag `lab-sim:20261012b` (image id `sha256:c17110ff…`); old tag kept, not overwritten. Built without the heavy-job lock under an explicit one-off exception from main (ORFS route held the lock; build was a cache hit up to the Python layer; VM memory watched: ~2.7 GB available throughout) | Reproduced arch's report in `lab-sim:20261012`: scalesim 3.0.0 `read_buffer.py:423 int(max(response_cycles_arr))` → `TypeError: only 0-dimensional arrays can be converted to Python scalars` on numpy 2.5.3. In `20261012b` the same run completes and two runs give the same COMPUTE_REPORT.csv sha256 (a758d5ac…); smoke 56/56 PASS incl. cocotb on Icarus + Verilator and the SCALE-Sim run. uv resolution with the two pins left pandas 3.0.6, matplotlib 3.11.2, ml_dtypes 0.6.0, cocotb 2.1.0 unchanged |

## Needs owner

_(none yet)_

## Requests

| From → To | What | Status |
|---|---|---|
| rtl → infra | lab-sim image needs `make`, `g++` (Verilator compiles its model with the host C++ compiler; cocotb Makefile flow) and `git`; please state the pinned cocotb / cocotb-coverage versions here (I am writing to cocotb 2.x + cocotb-coverage 2.0, latest on PyPI = 2.1.0 / 2.0) | **answered 02:58 (infra):** `make`, `g++`, `git` will be in lab-sim. Pins decided: **cocotb 2.1.0, cocotb-coverage 2.0, Python 3.12** (uv-managed), OSS CAD Suite 2026-09-28. **CONFIRMED 03:11 by test in the image** (`docker/lab-sim/selftest/run.sh`: cocotb 2.1.0 + cocotb-coverage 2.0 + numpy 2.5.3 on Python 3.12.15 pass on Verilator 5.053 and Icarus 14.0-devel, Makefile flow). One gotcha fixed in the image, see Decision 10: use plain `iverilog`/`vvp` from PATH, never `/opt/oss-cad-suite/bin/vvp` directly. **Rebuilt with the fix at 03:19** (image id `sha256:58972d79…`), both simulators pass. |
| pnr → infra | **ORFS image tag: please pull `openroad/orfs:26Q3-600-g3a964e13f` (digest `sha256:573c1716efa0e286c4f641c26d343e20929d58d27fffbb22be2d0b93f09764f6`, ~1.6 GB), NOT `latest`.** Reason: ORFS removed `rules-base.json`/`checkMetadata.py` (the shipped thresholds) on 2026-09-22 (commit 76be2a8e); every 26Q4-* tag incl. `latest` lacks them (checker now needs an online dashboard). 26Q3-600 is the newest tag still shipping them. Write it as `ORFS_IMAGE=openroad/orfs@sha256:573c...64f6` in coord/images.env. | **accepted 02:58 (infra):** tag + index digest verified against the registry (matches), pull in progress; see Decision 6. Note: 26Q3-605-g2d29bdaf8 is in fact the newest tag that still ships the rules files, but I am pulling 600 as you requested and authored against. |
| arch → infra | **lab-sim image breaks SCALE-Sim 3.0.0: numpy 2.5.3 raises `TypeError: only 0-dimensional arrays can be converted to Python scalars` (scalesim/memory/read_buffer.py:423, `int(max(arr))`; numpy ≥2.4 removed size-1-array→scalar conversion).** Please rebuild with `numpy==2.3.5` (what I developed against; also pin `numba==0.62.1` — 0.67 is untested with it; scalesim==3.0.0, pandas 3.0.6, matplotlib 3.11.2 ok). Full list of my working versions: `arch/requirements.lock` (python 3.11 there; 3.12 is fine as long as numpy is 2.3.x). Meanwhile I run the official check with a numpy 2.3.5 overlay only for development. | **done 03:38 (infra):** reproduced in `lab-sim:20261012` (same TypeError at read_buffer.py:423), re-locked with numpy 2.3.5 + numba 0.62.1 (llvmlite 0.45.1; everything else unchanged), new image **`lab-sim:20261012b`** — `source coord/images.env` again. Real SCALE-Sim run (google.cfg + alexnet_part) passes in it; before/after in `results/evidence/02_images_scalesim_numpy_fix.txt`. Decision 12. |
| infra → rtl (and all) | **`LAB_SIM_IMAGE` changed: `lab-sim:20261012` → `lab-sim:20261012b`** (numpy 2.5.3 → 2.3.5, numba 0.67.0 → 0.62.1, llvmlite 0.49.0 → 0.45.1; cocotb 2.1.0, cocotb-coverage 2.0, Python 3.12.15, simulators and all other tools identical). One image for everyone: scripts must take the ref from `coord/images.env`, never hard-code the tag. **Any official t1 results produced with the old tag must be re-run on `20261012b`** (the cocotb self-test passes on both simulators in the new image). `lab-sim:latest` now also points at the new image. | open 03:38 — rtl to acknowledge |
