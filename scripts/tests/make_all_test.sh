#!/bin/bash
# Unit test of scripts/make_all.py + make_all_failsoft_test.sh on a scratch git repo with fake, instant recipes.
# Usage: alltest.sh <dir with the real scripts/> <empty scratch dir>
SRC="$1"; T="$2"; cd "$T" || exit 2
mkdir -p scripts results/.stages rtl model docker
cp "$SRC/scripts/make_all.py" "$SRC/scripts/make_all_failsoft_test.sh" "$SRC/scripts/stage_inputs.json" scripts/
# the fake recipes write one marker per stage
python3 -c 'import json;p="scripts/stage_inputs.json";c=json.load(open(p));c["stages"]["t3"]["markers"]=["30_arch_model"];json.dump(c,open(p,"w"))'
echo "module a; endmodule" > rtl/a.sv; echo "x=1" > model/m.py; echo "FROM x" > docker/Dockerfile
for f in scripts/preflight.sh env.sh scripts/t1_run.sh scripts/t3_run.sh scripts/t2_run.sh scripts/repro.sh; do echo "# $f" > "$f"; done
# fake recipes: each appends its name to ran.log; a stage fails when FAIL_<name>=1; stages write their .done marker
cat > Makefile <<'EOF'
SHELL := /bin/bash
S := results/.stages
define STAGE
$(1):
	@echo $(1) >> ran.log; rm -f $(S)/$(2).done $(S)/$(2).failed; if [ "$$$${FAIL_$(3):-0}" = 1 ]; then echo x > $(S)/$(2).failed; exit 1; fi; : > $(S)/$(2).done
endef
$(eval $(call STAGE,preflight,00_preflight,preflight))
$(eval $(call STAGE,runtime,01_runtime,runtime))
$(eval $(call STAGE,images,02_images,images))
$(eval $(call STAGE,t1,10_rtl_verify,t1))
$(eval $(call STAGE,t2,20_pnr_ref,t2))
$(eval $(call STAGE,t2-stretch,xx_stretch,t2stretch))
$(eval $(call STAGE,t1-routed,11_eqy_routed,t1routed))
$(eval $(call STAGE,t3,30_arch_model,t3))
$(eval $(call STAGE,sweeps,41_sweeps_finish,sweeps))
$(eval $(call STAGE,repro,51_repro_full,repro))
demo:
	@echo demo >> ran.log; date +%s > demo_built; : > $(S)/60_demo.done
all:
	@MAKE="$(MAKE)" python3 scripts/make_all.py
EOF
git init -q . && git add -A && git -c user.email=t@example.invalid -c user.name=t commit -qm init
ran() { tr '\n' ' ' < ran.log; : > ran.log; }
ok() { if [ "$2" = "$3" ]; then echo "OK   $1"; else echo "FAIL $1: got [$2] want [$3]"; BAD=1; fi; }
BAD=0; : > ran.log
ALLS="preflight runtime images t1 t2 t2-stretch t1-routed t3 sweeps repro demo "

FAIL_t1=1 make all > out.A 2>&1; rc=$?
ok "A fail-soft: exit status" "$rc" "2"
ok "A fail-soft: every stage still ran, demo last" "$(ran)" "$ALLS"
ok "A fail-soft: failed stage listed" "$(grep -c 'stages that failed: t1$' out.A)" "1"

make all > out.B0 2>&1; ok "B full run: exit 0" "$?" "0"; ran > /dev/null
sleep 1
RESUME=1 make all > out.B 2>&1; rc=$?
ok "B resume, nothing changed: only demo ran" "$(ran)" "demo "
ok "B resume: exit 0" "$rc" "0"
ok "B resume: 10 skips logged with a reason" "$(grep -c 'SKIPPED — inputs' out.B)" "10"

echo "x=2" > model/m.py
RESUME=1 make all > out.C 2>&1
ok "C input of t3 changed: t3 + repro (depends on model/) + demo rerun" "$(ran)" "t3 repro demo "

RESUME=1 FORCE=1 make all > out.D 2>&1
ok "D FORCE=1 overrides RESUME" "$(ran)" "$ALLS"

python3 - <<'PY'
import glob, os
for f in glob.glob("results/.stages/make/*.json"): os.remove(f)
PY
sleep 1
RESUME=1 make all > out.E 2>&1
ok "E no make records: skip by .done marker mtime (t2-stretch has no stage marker, so it runs)" "$(ran)" "t2-stretch demo "
sleep 1; echo "module b; endmodule" > rtl/a.sv
RESUME=1 make all > out.F 2>&1
ok "F rtl/ touched after .done: t1, t2-stretch, t1-routed, repro rerun" "$(ran)" "t1 t2-stretch t1-routed repro demo "
ok "F reason names the newest file" "$(grep -c 'newest: rtl/a.sv' out.F)" "3"

echo x > results/.stages/30_arch_model.failed
RESUME=1 make all > out.G 2>&1
ok "G a .failed marker forces the stage to run" "$(ran)" "t3 demo "

make -n all > out.H 2>&1
ok "H make -n: nothing executed" "$(ran)" ""
ok "H make -n: nothing recorded" "$(grep -c 'nothing executed or recorded' out.H)" "1"

m0=$(stat -f %m results/.stages/00_preflight.done)
bash scripts/make_all_failsoft_test.sh preflight > out.I 2>&1; rc=$?
ok "I fail-soft self-test passes" "$rc" "0"
ok "I forced stage's recipe not run; rest skipped; demo ran twice (test + restore)" "$(ran)" "demo demo "
ok "I marker restored with its original mtime" "$(stat -f %m results/.stages/00_preflight.done)" "$m0"
ok "I no .failed marker left" "$(ls results/.stages | grep -c 'failed\|failsoft_saved')" "0"
ok "I result json pass" "$(python3 -c 'import json;d=json.load(open("results/make_all_failsoft.json"));print(d["pass"], d["make_all_exit_code"], d["not_run_forced_failure"], d["other_stages_that_failed_for_their_own_reasons"])')" "True 2 ['preflight'] []"
echo "x=3" > model/m.py
RESUME=markers make all > out.K 2>&1
ok "K marker-only mode ignores the changed input (t3 not rerun)" "$(ran)" "demo "
ok "K reason says what the input-aware rule would do" "$(grep -c 'would say: RUN' out.K)" "2"

FAIL_demo=0 FAIL_t2=1 FAIL_repro=1 make all > out.J 2>&1
ok "J two failures listed in order" "$(grep -c 'stages that failed: t2 repro$' out.J)" "1"; ran > /dev/null
echo; echo "--- sample: resume log (case C) ---"; cat out.C
echo "--- sample: fail-soft self-test output (case I) ---"; cat out.I
[ $BAD = 0 ] && echo "ALL make_all TESTS PASSED" || echo "SOME TESTS FAILED"
