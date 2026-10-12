#!/bin/bash
# Regenerates STATUS.md from budget.json + results/.stages markers + coord/next_action.txt.
# Agents never hand-edit STATUS.md: touch results/.stages/<stage>.{running,done,failed,blocked} instead.
LAB="$HOME/ai-chip-lab"; cd "$LAB" || exit 1
python3 - <<'PY'
import json,os,time,glob
b=json.load(open("budget.json")); now=int(time.time())
def hm(s): s=max(int(s),0); return "%dh%02dm"%(s//3600,(s%3600)//60)
st={}
for f in sorted(glob.glob("results/.stages/*.*")):
    n,ext=os.path.basename(f).rsplit(".",1); st.setdefault(ext,[]).append((n,open(f).read().strip()))
def lst(k): return ", ".join(n for n,_ in st.get(k,[])) or "-"
done={n for n,_ in st.get("done",[])}
running=[n for n,_ in st.get("running",[]) if n not in done]
sw=sum(sum(1 for _ in open(f)) for f in glob.glob("results/sweeps/*.jsonl"))
nxt=open("coord/next_action.txt").read().strip() if os.path.exists("coord/next_action.txt") else "-"
o=["# STATUS","",f"_updated {time.strftime('%F %T %Z')}_","",
f"- **Current stage(s):** {', '.join(running) or '-'}",f"- **Done:** {lst('done')}",
f"- **Failed:** {lst('failed')}",f"- **BLOCKED:** {lst('blocked')}",
f"- **Elapsed:** {hm(now-b['start_epoch'])} of {b['total_budget_h']}h",
f"- **Remaining:** {hm(b['deadline_final_epoch']-now)} total; {hm(b['deadline_sweeps_stop_epoch']-now)} until sweeps must stop",
f"- **Sweep points recorded:** {sw}",f"- **Next action:** {nxt}",""]
for k in ("failed","blocked"):
    for n,msg in st.get(k,[]):
        o+=[f"## {k.upper()}: {n}","```",msg,"```",""]
open("STATUS.md","w").write("\n".join(o))
PY
