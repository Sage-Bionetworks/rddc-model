"""The orchestrator: work out what to dispatch next for a batch.

Usage:
  python scripts/orchestrate.py SIDECAR --register REGISTER [--state PLAN] [-o PLAN] [--rules RULES]
  python scripts/orchestrate.py SIDECAR --register REGISTER --simulate [--rules RULES]

Inputs: the batch's sidecar; the source register (the batch's source must have an
entry); the rule set (default rules/rules.yaml), which must pin the release the sidecar
declares in conformsTo; and the batch state so far, which is the plan this script last
wrote with the dispatcher's updates (step status, and each file's output location and
reported properties). With no state, the batch has just arrived.

Each call
1. replays the steps that ran (rules/route.lp). If any broke a rule, the batch is
   stopped and nothing is dispatched;
2. plans, from where each file is now, the shortest continuation to its target that
   breaks no rule (rules/plan.lp). A file with none is blocked, and so is a file whose
   last step failed; files with a step running wait;
3. writes the plan: groups of files with the steps that ran and the steps to come.
   Each ready step has what the dispatcher needs: runner, pipeline, input locations,
   output location and parameters (from the sidecar and the source register).

--simulate runs a stub dispatcher: it marks every ready step succeeded, with outputs at
the step's output location, and calls the orchestrator again until nothing is ready,
printing each round.
"""

import argparse
import copy
import hashlib
import json
import os
import re
import sys

from linkml.validator import validate

import rules_engine as E

SCHEMA = os.path.join(E.ROOT, "schema", "processing.yaml")
HISTORY = ("succeeded", "running", "failed")


class OrchestrationError(Exception):
    pass


def fail(msg):
    raise OrchestrationError(msg)


def rule_name(rule):
    return rule if isinstance(rule, str) else " ".join(str(a) for a in rule)


# --- inputs ---------------------------------------------------------------------

def prepare(sidecar, rules, register):
    tag = E.sidecar_release(sidecar)
    if tag != rules["modelRelease"]:
        fail(f"the sidecar declares release {tag}, but the rule set pins {rules['modelRelease']}")
    entry = E.register_entry(register, sidecar.get("sourceId"))
    if entry is None:
        fail(f"source {sidecar.get('sourceId')} is not in the source register")
    rel = E.Release(tag)
    errs = E.name_errors(rules, rel)
    if errs:
        fail("the rule set does not check:\n  " + "\n  ".join(errs))
    return rel, entry, E.sidecar_files(sidecar, entry, rules, rel)


def history(state, files):
    """Each file's steps so far, in order: the step dicts from the state."""
    known = {f["id"] for f in files}
    out = {f["id"]: [] for f in files}
    for g in (state or {}).get("groups", []):
        for s in g.get("steps", []):
            if s["status"] not in HISTORY:
                continue
            for fid in g["files"]:
                if fid not in known:
                    fail(f"the state names {fid}, which is not a data file of the batch")
                if all(h["dispatchId"] != s["dispatchId"] for h in out[fid]):
                    out[fid].append(s)
    return out


def history_facts(hist, rules):
    """go/done facts for the steps that ran or are running, and observed properties."""
    bits = E.prop_bits(rules)
    facts = []
    for fid, steps in hist.items():
        for t, s in enumerate(steps):
            if s["status"] == "failed":
                break
            facts.append(f"done({E.q(fid)}, {t}, {E.q(s['workflow'])}).")
            result = next((r for r in s.get("results", []) if r["file"] == fid), None)
            if result is not None and "properties" in result:
                unknown = set(result["properties"]) - set(bits)
                if unknown:
                    fail(f"step {s['dispatchId']} reports unknown properties {sorted(unknown)}")
                mask = sum(bits[p] for p in result["properties"])
                facts.append(f"observed({E.q(fid)}, {t + 1}, {mask}).")
    return "\n".join(facts)


def current_location(f, steps):
    """Where the file's data is after its succeeded steps: {file, location, dataset?}."""
    out = {"file": f["id"], "location": f["location"]}
    for s in steps:
        if s["status"] != "succeeded":
            break
        result = next((r for r in s.get("results", []) if r["file"] == f["id"]), {})
        if not (result.get("location") or result.get("dataset") or s.get("outputLocation")):
            continue  # the step wrote no data (a check or review), so the data stays put
        out = {"file": f["id"], "location": result.get("location") or s.get("outputLocation") or out["location"]}
        if result.get("dataset"):
            out["dataset"] = result["dataset"]
    return out


# --- reasoning ------------------------------------------------------------------

def replay(facts):
    """Rules the steps that ran break: [(file, step, rule)]."""
    go = facts.replace("done(", "go(")
    found = E.by_name(E.solve(["engine.lp", "route.lp"], go))
    return sorted((x, t, rule_name(r)) for r, x, t in found.get("rviolation", []) if r != "not_at_target")


def continue_routes(facts):
    """Each file's full route (steps so far, then planned), its target, and stuck files."""
    models = E.solve(["engine.lp", "route.lp", "plan.lp"], facts, optimal=True)
    if not models:
        fail("the rules program has no answer for this batch")
    plans = []
    for m in models:
        found = E.by_name(m)
        route = {}
        for x, t, w in sorted(found.get("go", [])):
            route.setdefault(x, []).append(w)
        plans.append((route, dict(found.get("ftarget", [])), {x for (x,) in found.get("stuck", [])}))
    if any(p[0] != plans[0][0] for p in plans[1:]):
        diff = sorted({x for p in plans for x in p[0] if p[0].get(x) != plans[0][0].get(x)})
        fail("routes tie for: " + ", ".join(diff) + "; set workflow priorities to break the tie")
    return plans[0]


# --- output ---------------------------------------------------------------------

def param(p, sidecar, file_set, entry, did=None):
    if "value" in p:
        value = str(p["value"])
        if did is not None:
            value = value.format(sourceId=sidecar["sourceId"], batchId=sidecar["batchId"], dispatchId=did)
        return {"id": p["id"], "value": value}
    if "fromSourceRegister" in p:
        source, field, where = entry, p["fromSourceRegister"], "the source register entry"
    else:
        scope, _, field = p["fromSidecar"].partition(".")
        source, where = (sidecar, "the sidecar") if scope == "batch" else (file_set, "the file set")
    if source is None or field not in source:
        fail(f"parameter {p['id']} needs {field}, which {where} does not have")
    v = source[field]
    return {"id": p["id"], "value": v if isinstance(v, str) else json.dumps(v)}


def dispatch_id(wid, fids, prior):
    key = json.dumps([wid, sorted(fids), [s["dispatchId"] for s in prior]])
    return f"{wid}-{hashlib.sha256(key.encode()).hexdigest()[:10]}"


def new_step(rules, wid, status, sidecar, file_set, entry, fids=(), prior=(), inputs=None):
    w = next(x for x in rules["workflows"] if x["id"] == wid)
    out = {"workflow": wid, "status": status, "runner": w["runner"]}
    for k in ("cirroProcess", "cirroExecutor", "pipeline", "pipelineVersion"):
        if k in w:
            out[k] = w[k]
    if status == "ready":
        did = dispatch_id(wid, fids, prior)
        zone = next((z for z in rules["zones"] if z["id"] == w.get("writesTo")), {})
        out["dispatchId"] = did
        if w["runner"] == "cirro":
            # A Cirro run: the output is a new dataset in the zone's environment; an analysis
            # reads its inputs' datasets, an ingest uploads the input files.
            out["cirroEnvironment"] = zone["cirroEnvironment"]
        if inputs:
            out["inputs"] = inputs
        if w["runner"] == "cirro" and w.get("cirroExecutor") != "INGEST" and inputs:
            missing = [i["file"] for i in inputs if "dataset" not in i]
            if missing:
                fail(f"{wid} is a Cirro analysis, but these inputs are in no Cirro dataset: {missing}")
            out["sourceDatasets"] = sorted({i["dataset"] for i in inputs})
        if "location" in zone and "cirroEnvironment" not in zone:
            out["outputLocation"] = zone["location"].format(
                sourceId=sidecar["sourceId"], batchId=sidecar["batchId"], dispatchId=did)
        params = [param(p, sidecar, file_set, entry, did) for p in w.get("parameters", [])]
        if params:
            out["parameters"] = params
    return out


def orchestrate(sidecar, rules, register, state=None):
    """The new plan for the batch, given the state so far."""
    rel, entry, files = prepare(sidecar, rules, register)
    hist = history(state, files)
    facts = "\n".join([E.catalog_facts(rules, rel), E.file_facts(files), history_facts(hist, rules)])
    plan = {
        "batch": sidecar["name"],
        "sidecarConformsTo": next(u for u in sidecar["conformsTo"] if E.SIDECAR_VERSION.match(u)),
        "ruleSet": rules["id"], "ruleSetVersion": rules["version"], "modelRelease": rules["modelRelease"],
        "registerVersion": register["registerVersion"],
    }
    if state and state.get("ruleSetVersion") not in (None, rules["version"]):
        fail(f"the batch started under rule set version {state['ruleSetVersion']}, not {rules['version']}")
    broken = replay(facts) if files else []
    if broken:
        plan["status"] = "stopped"
        plan["problems"] = [f"{x}, step {t}: {r}" for x, t, r in broken]
        plan["groups"] = (state or {}).get("groups", [])
        return check_schema(plan)

    # Files with a step running are planned as if it succeeded (nothing is dispatched
    # for them until it does); files whose last step failed are not planned.
    failed = {fid for fid, steps in hist.items() if steps and steps[-1]["status"] == "failed"}
    active = "\n".join(f"active({E.q(f['id'])})." for f in files if f["id"] not in failed)
    route, target, stuck = continue_routes(facts + "\n" + active) if files else ({}, {}, set())

    sets = {d["@id"]: d for d in sidecar.get("distribution", []) if d.get("@type") == "cr:FileSet"}
    groups = {}
    for f in files:
        steps = hist[f["id"]]
        future = route.get(f["id"], [])[len([s for s in steps if s["status"] != "failed"]):]
        last = steps[-1]["status"] if steps else None
        why = (f"step {steps[-1]['dispatchId']} failed" if last == "failed"
               else "no route from the current state to the target" if f["id"] in stuck else None)
        key = (f["fileSet"], tuple(s["dispatchId"] for s in steps), tuple(future), target.get(f["id"]), why)
        groups.setdefault(key, []).append(f)
    out = []
    for (fs, _, future, tgt, why), members in groups.items():
        fids = [f["id"] for f in members]
        prior = hist[fids[0]]
        gid = re.sub(r"[^A-Za-z0-9_]", "_", f"{fs or 'files'}_{tgt}")
        while any(g["id"] == gid for g in out):
            gid += "_2"
        steps = [copy.deepcopy(s) for s in prior]
        waiting = bool(prior) and prior[-1]["status"] in ("running", "failed")
        for i, wid in enumerate(future):
            if i == 0 and not waiting and not why:
                inputs = [current_location(f, prior) for f in members]
                steps.append(new_step(rules, wid, "ready", sidecar, sets.get(fs), entry, fids, prior, inputs))
            else:
                steps.append(new_step(rules, wid, "pending", sidecar, sets.get(fs), entry))
        g = {"id": gid, "files": fids, "target": tgt, "steps": steps}
        if fs:
            g["fileSet"] = fs
        if why:
            g["problems"] = [why]
        out.append(g)
    plan["groups"] = out

    old_batch = {s["workflow"]: s for s in (state or {}).get("batchSteps", [])}
    batch = [old_batch.get(r["workflow"]) or new_step(rules, r["workflow"], "ready", sidecar, None, entry,
                                                      [sidecar["batchId"]])
             for r in rules.get("interactionRules", []) if r["interaction"] == sidecar.get("interaction")]
    if batch:
        plan["batchSteps"] = batch
    statuses = [s["status"] for g in out for s in g["steps"]] + [s["status"] for s in batch]
    plan["status"] = ("in_progress" if any(s in ("ready", "running", "pending") for s in statuses)
                      else "blocked" if any("problems" in g for g in out) else "complete")
    return check_schema(plan)


def check_schema(plan):
    report = validate(plan, SCHEMA, "Plan")
    if report.results:
        fail("the plan does not validate:\n  " + "\n  ".join(r.message for r in report.results))
    return plan


def ready_steps(plan):
    for g in plan.get("groups", []):
        for s in g["steps"]:
            if s["status"] == "ready":
                yield g, s
    for s in plan.get("batchSteps", []):
        if s["status"] == "ready":
            yield None, s


def stub_dispatch(plan, report=None):
    """Mark every ready step succeeded, as a dispatcher would after the runs finish.
    report(group, step) may return results ([{file, location?, dataset?, properties?}]).
    A Cirro step reports its new dataset for each file, as Cirro would."""
    plan = copy.deepcopy(plan)
    for g, s in ready_steps(plan):
        s["status"] = "succeeded"
        results = (report(g, s) if report else None) or []
        if s["runner"] == "cirro" and g is not None:
            ds = f"stub-dataset-{s['dispatchId']}"
            by_file = {r["file"]: r for r in results}
            results = [dict({"file": f, "dataset": ds, "location": f"s3://{s['cirroEnvironment']}/datasets/{ds}/data/"},
                            **by_file.get(f, {})) for f in g["files"]]
        if results:
            s["results"] = results
    return plan


def summary(plan):
    lines = [f"status {plan['status']}"]
    for g in plan.get("groups", []):
        route = " -> ".join(f"{s['workflow']}[{s['status']}]" for s in g["steps"]) or "(nothing to run)"
        lines.append(f"  {g['id']} ({len(g['files'])} file(s)): {route}")
        lines += [f"    problem: {p}" for p in g.get("problems", [])]
    for s in plan.get("batchSteps", []):
        lines.append(f"  batch: {s['workflow']}[{s['status']}]")
    lines += [f"  problem: {p}" for p in plan.get("problems", [])]
    return "\n".join(lines)


def main():
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("sidecar")
    ap.add_argument("--register", required=True)
    ap.add_argument("--state")
    ap.add_argument("-o", "--output")
    ap.add_argument("--rules")
    ap.add_argument("--simulate", action="store_true")
    args = ap.parse_args()
    sidecar, rules = json.load(open(args.sidecar)), E.load_rules(args.rules)
    register = json.load(open(args.register))
    state = json.load(open(args.state)) if args.state else None
    try:
        plan = orchestrate(sidecar, rules, register, state)
        if args.simulate:
            n = 0
            print(f"round {n}: {summary(plan)}")
            while any(True for _ in ready_steps(plan)):
                n += 1
                plan = orchestrate(sidecar, rules, register, stub_dispatch(plan))
                print(f"round {n}: {summary(plan)}")
            return
    except OrchestrationError as e:
        sys.exit(f"error: {e}")
    text = json.dumps(plan, indent=2) + "\n"
    if args.output:
        open(args.output, "w").write(text)
    else:
        sys.stdout.write(text)


if __name__ == "__main__":
    main()
