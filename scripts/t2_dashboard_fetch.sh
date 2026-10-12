#!/bin/bash
# t2_dashboard_fetch.sh -- re-fetch ORFS's public QoR dashboard measurement of the pinned commit (read-only GETs).
# Writes results/t2/published/{commit_lookup.json,dashboard_commit_3a964e13f_metrics_raw.json,retrieved_utc.txt,sha256.txt};
# the per-design files dashboard_<platform>_gcd_raw.json are cut from the raw payload by the python step below.
# Commit id 25781 = sha 3a964e13f11a4e435aac01ffa14db0a7d2853720 (lookup: GET /api/commits?search=<sha>).
set -eu
LAB="$HOME/ai-chip-lab"; D="$LAB/results/t2/published"; B=https://dashboard.precisioninno.com/api
SHA=3a964e13f11a4e435aac01ffa14db0a7d2853720; mkdir -p "$D"
curl -sf -m 60 "$B/commits?search=${SHA:0:9}" -o "$D/commit_lookup.json"
ID=$(python3 -c "import json;print([i['id'] for i in json.load(open('$D/commit_lookup.json'))['items'] if i['hash']=='$SHA'][0])")
curl -sf -m 180 "$B/commits/$ID/metrics" -o "$D/dashboard_commit_3a964e13f_metrics_raw.json"
date -u +%FT%TZ > "$D/retrieved_utc.txt"
python3 - "$D" <<'P'
import json, sys, hashlib, os
D = sys.argv[1]; raw = json.load(open(f"{D}/dashboard_commit_3a964e13f_metrics_raw.json"))
for p in raw["platforms"]:
    if p["platformName"] in ("nangate45", "sky130hd"):
        for g in p["designs"]:
            if g["designName"] == "gcd":
                json.dump({"source": f"https://dashboard.precisioninno.com/api/commits/{raw['commitId']}/metrics", "commit": raw["sha"],
                           "platform": p["platformName"], "design": g}, open(f"{D}/dashboard_{p['platformName']}_gcd_raw.json", "w"), indent=1)
open(f"{D}/sha256.txt", "w").write("".join(f"{hashlib.sha256(open(f'{D}/{f}','rb').read()).hexdigest()}  {f}\n" for f in sorted(os.listdir(D)) if f.endswith(".json")))
P
cat "$D/sha256.txt"
