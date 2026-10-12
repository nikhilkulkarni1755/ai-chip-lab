#!/usr/bin/env python3
"""Negative control inside a per-PE cone of the ROUTED netlist (stage 11_eqy_routed, reviewer caveat).

  p2_negcone.py mutate <netlist.v> <out.v> <info.json> [acc_o bit=5]
      Change the function of ONE standard cell in the combinational fan-in of the accumulator
      register that drives output bit acc_o[bit] (the fan-in is searched backwards from the
      register's D pin and stops at flip-flops, so the cell is inside that PE's cone by
      construction).  The cell type is replaced by a pin-compatible type with a different
      function (AND2<->OR2, NAND2<->NOR2, ...); nothing else in the netlist changes.
  p2_negcone.py result <eqy dir> <partition> <info.json> <eqy exit code> <seconds> <out.json>
      Read how EQY/the solver treated that partition and write the result JSON.
"""
import json
import re
import sys

SWAP = {"AND2_X1": "OR2_X1", "OR2_X1": "AND2_X1", "NAND2_X1": "NOR2_X1", "NOR2_X1": "NAND2_X1",
        "AND3_X1": "OR3_X1", "OR3_X1": "AND3_X1", "NAND3_X1": "NOR3_X1", "NOR3_X1": "NAND3_X1",
        "AOI21_X1": "OAI21_X1", "OAI21_X1": "AOI21_X1"}
OUT_PINS = {"Z", "ZN", "Q", "QN", "CO", "S"}
INST = re.compile(r"^\s*([A-Z][A-Z0-9]*_X\d+)\s+(\S+)\s*\((.*?)\);", re.S | re.M)
PIN = re.compile(r"\.(\w+)\(\s*([^)]*?)\s*\)")


def mutate(src, dst, info_path, bit):
    text = open(src).read()
    cells, driver = [], {}
    for m in INST.finditer(text):
        pins = dict(PIN.findall(m.group(3)))
        c = {"type": m.group(1), "name": m.group(2), "pins": pins, "span": m.span(1)}
        cells.append(c)
        for p, net in pins.items():
            if p in OUT_PINS and net:
                driver[net] = c
    port = f"acc_o[{bit}]"
    c = driver.get(port)
    hops = []
    while c is not None and not c["type"].startswith("DFF"):      # output buffer chain
        hops.append(c["name"])
        if not c["type"].startswith(("BUF", "CLKBUF")):
            sys.exit(f"mutate: {port} is driven through a non-buffer cell {c['type']} {c['name']}")
        c = driver.get(c["pins"]["A"])
    if c is None:
        sys.exit(f"mutate: no flip-flop found behind {port}")
    flop = c
    # breadth-first search backwards from the flop's D pin, combinational cells only
    seen, frontier, depth, target = set(), [flop["pins"]["D"]], 0, None
    while frontier and target is None:
        depth += 1
        nxt = []
        for net in frontier:
            d = driver.get(net)
            if d is None or d["type"].startswith("DFF") or d["name"] in seen:
                continue
            seen.add(d["name"])
            if depth >= 3 and d["type"] in SWAP and target is None:
                target = (d, depth)
            nxt += [n for p, n in d["pins"].items() if p not in OUT_PINS and n]
        frontier = nxt
    if target is None:
        sys.exit("mutate: no pin-compatible cell found in the cone")
    cell, depth = target
    a, b = cell["span"]
    out = text[:a] + SWAP[cell["type"]] + text[b:]
    open(dst, "w").write(out)
    changed = sum(1 for x, y in zip(text.splitlines(), out.splitlines()) if x != y)
    info = {"output_bit": port, "accumulator_flop": flop["name"], "output_buffers": hops,
            "mutated_cell": cell["name"], "cell_type_before": cell["type"], "cell_type_after": SWAP[cell["type"]],
            "cell_pins": cell["pins"], "combinational_depth_before_flop_D": depth,
            "netlist_lines_changed": changed,
            "how_chosen": "first pin-compatible cell at depth >= 3 in a breadth-first search backwards from the D pin of "
                          "the accumulator register behind this output bit, stopping at flip-flops"}
    json.dump(info, open(info_path, "w"), indent=1)
    print(json.dumps(info, indent=1))
    if changed != 1:
        sys.exit("mutate: expected exactly one changed line")


def read(p):
    try:
        return open(p, errors="replace").read()
    except OSError:
        return ""


def result(d, part, info_path, rc, secs, out, depth="2"):
    log = read(f"{d}/logfile.txt")
    sdir = f"{d}/strategies/{part}/smt"
    slog = read(f"{sdir}/{part}/logfile.txt")
    sstat = (read(f"{sdir}/status").split() or ["none"])[0]
    base = re.search(r"returned (\w+) for basecase", slog)
    ind = re.search(r"returned (\w+) for induction", slog)
    el = re.search(r"Elapsed clock time.*\((\d+)\)", slog)
    m = re.search(r"Could not prove equivalence of partition '%s' using strategy 'smt': (.*)" % re.escape(part), log)
    proved = bool(re.search(r"Proved equivalence of partition '%s'" % re.escape(part), log))
    if int(rc) == 124 or sstat == "none":
        how = "no result: the solver did not finish within the lock hold (says nothing either way)"
        rejected = None
    elif proved or sstat == "PASS":
        how = "NOT rejected: the mutated netlist was proven equivalent (the control failed)"
        rejected = False
    elif sstat == "FAIL":
        how = "counterexample: the solver found an input sequence on which RTL and mutated netlist differ"
        rejected = True
    elif sstat == "UNKNOWN" and ind and ind.group(1) == "FAIL":
        how = (f"not proven equivalent: the depth-{depth} base case passes and the induction step fails with a "
               "counterexample-to-induction trace (solver finished, no timeout); this is weaker than a counterexample")
        rejected = True
    else:
        how = f"not proven equivalent: solver status {sstat}"
        rejected = True
    r = {"name": "eqy_neg_netlist_cone", "stage": "11_eqy_routed",
         "what": "one cell function changed inside a per-PE cone of the routed netlist; only that PE's partition is solved",
         "partition": part, "mutation": json.load(open(info_path)),
         "eqy_exit_code": int(rc), "eqy_message": m.group(1).strip() if m else None,
         "solver_status": sstat, "basecase": base.group(1) if base else None,
         "induction": ind.group(1) if ind else None, "solver_seconds": int(el.group(1)) if el else None,
         "hold_seconds": int(secs), "rejected": rejected, "rejected_as": how,
         "depth": int(depth),
         "engine": "sby smtbmc bitwuzla, depth %s%s" % (depth, " (same strategy as the proof)" if depth == "2" else
                                                        " (the proof's strategy with a deeper bounded check, used for this control only)"),
         "command": ("" if depth == "2" else f"NEGCONE_DEPTH={depth} ") + "scripts/p2_negcone.sh"}
    json.dump(r, open(out, "w"), indent=1)
    open(out, "a").write("\n")
    print(json.dumps({k: r[k] for k in ("partition", "solver_status", "basecase", "induction", "rejected", "rejected_as")}, indent=1))
    return 0 if rejected else 1


if __name__ == "__main__":
    if sys.argv[1] == "mutate":
        mutate(sys.argv[2], sys.argv[3], sys.argv[4], int(sys.argv[5]) if len(sys.argv) > 5 else 5)
    else:
        sys.exit(result(*sys.argv[2:9]))
