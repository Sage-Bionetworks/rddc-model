"""Cirro process specs and links, from the rule set.

Usage:
  python scripts/cirro_links.py            check the committed specs and the links
  python scripts/cirro_links.py --write    regenerate rules/cirro/specs/
  python scripts/cirro_links.py --refresh-catalog
                                           refresh rules/cirro/catalog.json from Cirro
                                           (needs the cirro SDK and a saved login)

In Cirro, a pipeline can run on a dataset only if the process that made the dataset (a
data type, for an ingest, or another pipeline) and the pipeline are linked: the producer
lists the pipeline in childProcessIds, or the pipeline lists the producer in
parentProcessIds. Cirro shows a link declared on either side.

The links the rules need come from the routes: for every deposit a reader can describe,
the route to its target and the routes to the release and public zones. Along a route,
each Cirro analysis reads the dataset written by the last step that wrote data. That
step is a Cirro pipeline, or the ingest, in which case the producer is any data type
the ingest may choose for the deposit's class.

For each process that is not in Cirro yet (a data type or workflow marked to_add), a
spec is generated in rules/cirro/specs/<id>.json: the body of POST /processes
(CustomProcessInput), with its links, file rules and environments. Processes already in
Cirro are described by rules/cirro/catalog.json, a snapshot of their links.

The check fails if a spec is missing or out of date, if a process marked available is
not in the catalog, or if a link the routes need is declared on neither side.
"""

import argparse
import json
import os
import sys

import rules_engine as E

CIRRO_DIR = os.path.join(E.RULES_DIR, "cirro")
SPECS_DIR = os.path.join(CIRRO_DIR, "specs")
CATALOG = os.path.join(CIRRO_DIR, "catalog.json")


def workflows(rules):
    return {w["id"]: w for w in rules["workflows"]}


def ingest_types(rules):
    return [t for w in rules["workflows"] for t in w.get("cirroIngestTypes", [])]


def candidates(rules, rel, cls):
    """Data types the ingest may choose for a file of this class (file names, techniques
    and platforms decide among them)."""
    return {t["dataType"] for t in ingest_types(rules) if any(rel.is_a(cls, c) for c in t["classes"])}


def route_links(rules, rel, cls, route):
    """(producer, consumer, workflow) for each Cirro analysis on a route from a deposit of
    this class. producer and consumer are Cirro process ids."""
    wfs, out, producers = workflows(rules), [], set()
    for wid in route:
        w = wfs[wid]
        cirro = w["runner"] == "cirro"
        ingest = cirro and w.get("cirroExecutor") == "INGEST"
        if cirro and not ingest:
            out += [(p, w["cirroProcess"], wid) for p in sorted(producers)]
        if w["kind"] in E.NO_DATA_KINDS:
            continue
        producers = (candidates(rules, rel, cls) if ingest else {w["cirroProcess"]} if cirro else set())
    return out


def required_links(rules, rel, routes=None):
    """{(producer, consumer): an example (class, route)} for every route the rules allow
    from every deposit a reader can describe."""
    if routes is None:
        deposits = list({json.dumps(d, sort_keys=True, default=list): d for d in E.deposit_space(rules, rel)}.values())
        routes = [(d[1], r) for d, r in zip(deposits, E.deposit_routes(rules, rel, deposits))]
    links = {}
    for cls, r in routes:
        for route in ([w for w, _ in r["path"]] if r["path"] else None, r["release"], r["public"]):
            for p, c, _ in route_links(rules, rel, cls, route or []):
                links.setdefault((p, c), (cls, route))
    return links


def processes(rules, rel):
    """{process id: availability} for every Cirro process the rules name."""
    out = {t["dataType"]: rel.cirro_data_types.get(t["dataType"]) for t in ingest_types(rules)}
    for w in rules["workflows"]:
        if w.get("cirroProcess"):
            out[w["cirroProcess"]] = w.get("cirroAvailability")
    return out


def environments(rules, zone_ids):
    zones = {z["id"]: z for z in rules["zones"]}
    return sorted({zones[z]["cirroEnvironment"] for z in zone_ids if "cirroEnvironment" in zones.get(z, {})})


def specs(rules, rel, links):
    """{process id: CustomProcessInput body} for every process marked to_add."""
    avail = processes(rules, rel)
    repos = {r["id"]: r for r in rules.get("pipelineRepositories", [])}
    children, parents = {}, {}
    for p, c in links:
        children.setdefault(p, set()).add(c)
        parents.setdefault(c, set()).add(p)
    out = {}
    for w in rules["workflows"]:
        for t in w.get("cirroIngestTypes", []):
            dt = t["dataType"]
            if avail[dt] != "to_add" or dt in out:
                continue
            out[dt] = {
                "id": dt,
                "name": rel.cirro_data_type_titles.get(dt) or dt,
                "description": f"RDDC data type: {rel.cirro_data_type_titles.get(dt) or dt}, uploaded by {w['id']}.",
                "executor": "INGEST",
                "childProcessIds": sorted(children.get(dt, ())),
                "parentProcessIds": [],
                "linkedProjectIds": environments(rules, [w["writesTo"]]),
                "isTenantWide": False,
                "fileMappingRules": [
                    {"description": r["description"], "min": r["minFiles"], "max": r.get("maxFiles", r["minFiles"]),
                     "fileNamePatterns": [{"exampleName": fp.get("exampleName", ""), "description": fp.get("description", ""),
                                           "sampleMatchingPattern": fp["namePattern"]} for fp in r["fileNamePatterns"]]}
                    for r in t["fileRules"]],
            }
    for w in rules["workflows"]:
        pid = w.get("cirroProcess")
        if not pid or w.get("cirroAvailability") != "to_add":
            continue
        spec = out.setdefault(pid, {
            "id": pid, "name": "", "description": "", "executor": w["cirroExecutor"],
            "childProcessIds": sorted(children.get(pid, ())), "parentProcessIds": sorted(parents.get(pid, ())),
            "linkedProjectIds": [], "isTenantWide": False, "dataType": "",
        })
        # Workflows that share a process (one pipeline, run with different parameters)
        # share its spec.
        spec["name"] = ", ".join(filter(None, [spec["name"], w["id"]]))
        spec["description"] = " ".join(filter(None, [spec["description"], " ".join(w.get("description", "").split())]))
        spec["dataType"] = spec["dataType"] or f"{w.get('produces') or w['id']} ({w['id']})"
        repo = repos.get(w.get("pipelineRepository"))
        if repo and "pipelineCode" not in spec:
            # Code in workflows/<name>/, Cirro configuration in .cirro/<name>/, one tag per
            # pipeline version (see PipelineRepository).
            name, tag = w["pipelineName"], f"{w['pipelineName']}/v{w['pipelineVersion']}"
            main = "main.wdl" if w["cirroExecutor"] == "CROMWELL" else "main.nf"
            spec["pipelineCode"] = {"repositoryPath": repo["repository"], "version": tag,
                                    "repositoryType": repo["repositoryType"], "entryPoint": f"workflows/{name}/{main}"}
            spec["customSettings"] = {"repository": repo["repository"], "branch": tag, "folder": f".cirro/{name}",
                                      "repositoryType": repo["repositoryType"]}
        spec["linkedProjectIds"] = sorted(set(spec["linkedProjectIds"])
                                          | set(environments(rules, w.get("readsFrom", []) + [w["writesTo"]])))
    return out


def load_catalog():
    return json.load(open(CATALOG)) if os.path.exists(CATALOG) else {"processes": {}}


def load_specs():
    if not os.path.isdir(SPECS_DIR):
        return {}
    return {f[:-5]: json.load(open(os.path.join(SPECS_DIR, f))) for f in sorted(os.listdir(SPECS_DIR))
            if f.endswith(".json")}


def link_errors(rules, rel, links, committed, catalog):
    """Problems with the Cirro processes and links, given the committed specs and the
    catalog snapshot."""
    errs = []
    avail = processes(rules, rel)
    known = catalog.get("processes", {})
    for pid, a in sorted(avail.items()):
        if a == "available" and pid not in known:
            errs.append(f"Cirro process {pid} is marked available but is not in rules/cirro/catalog.json "
                        "(refresh the catalog, or mark it to_add)")
    expected = specs(rules, rel, links)
    for pid in sorted(set(expected) | set(committed)):
        if pid not in committed:
            errs.append(f"no spec for {pid}, which is not in Cirro yet; run scripts/cirro_links.py --write")
        elif pid not in expected:
            errs.append(f"spec {pid}.json is for a process the rules no longer mark to_add; run --write")
        elif committed[pid] != expected[pid]:
            errs.append(f"spec {pid}.json is out of date; run scripts/cirro_links.py --write")

    def side(pid, key):
        return set((committed.get(pid) or known.get(pid) or {}).get(key, []))

    for (p, c), (cls, route) in sorted(links.items()):
        if c not in side(p, "childProcessIds") and p not in side(c, "parentProcessIds"):
            errs.append(f"no Cirro link from {p} to {c}, which a {cls} file needs on the route {' -> '.join(route)}")
    return errs


def refresh_catalog(rules, rel):
    from cirro import CirroApi  # only here: the checks do not need the SDK
    api = CirroApi()
    by_id = {p.id: p for p in api.processes.list()}
    out = {}
    for pid, a in sorted(processes(rules, rel).items()):
        if a != "available":
            continue
        if pid not in by_id:
            sys.exit(f"error: {pid} is marked available but Cirro has no such process")
        d = api.processes.get(pid)
        # Links declared by other processes count too (Cirro shows either side).
        parents = set(d.parent_process_ids or []) | {q.id for q in by_id.values() if pid in (q.child_process_ids or [])}
        children = set(d.child_process_ids or []) | {q.id for q in by_id.values() if pid in (q.parent_process_ids or [])}
        out[pid] = {"name": d.name, "executor": str(d.executor), "parentProcessIds": sorted(parents),
                    "childProcessIds": sorted(children)}
    from datetime import date
    os.makedirs(CIRRO_DIR, exist_ok=True)
    with open(CATALOG, "w") as f:
        json.dump({"retrieved": date.today().isoformat(),
                   "source": f"Cirro Data API at {api.configuration.base_url}, GET /processes",
                   "processes": out}, f, indent=2)
        f.write("\n")
    print(f"wrote {CATALOG} ({len(out)} processes)")


def main():
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--write", action="store_true")
    ap.add_argument("--refresh-catalog", action="store_true")
    args = ap.parse_args()
    rules = E.load_rules()
    rel = E.Release(rules["modelRelease"])
    if args.refresh_catalog:
        refresh_catalog(rules, rel)
        return
    links = required_links(rules, rel)
    if args.write:
        os.makedirs(SPECS_DIR, exist_ok=True)
        expected = specs(rules, rel, links)
        for f in os.listdir(SPECS_DIR):
            if f.endswith(".json") and f[:-5] not in expected:
                os.remove(os.path.join(SPECS_DIR, f))
        for pid, spec in expected.items():
            with open(os.path.join(SPECS_DIR, pid + ".json"), "w") as f:
                json.dump(spec, f, indent=2)
                f.write("\n")
        print(f"wrote {len(expected)} specs to {SPECS_DIR} ({len(links)} links)")
        return
    committed, catalog = load_specs(), load_catalog()
    errs = link_errors(rules, rel, links, committed, catalog)
    for e in errs:
        print("FAIL", e)
    print(f"{len(links)} Cirro links needed; {len(errs)} problem(s)")
    missed = seeded_cases(rules, rel, links, committed, catalog)
    sys.exit(1 if errs or missed else 0)


def seeded_cases(rules, rel, links, committed, catalog):
    """Broken specs and rules the check must catch. Returns how many it missed."""
    import copy

    def drop_child(specs, pid, child):
        specs = copy.deepcopy(specs)
        specs[pid]["childProcessIds"].remove(child)
        specs[child]["parentProcessIds"] = [p for p in specs[child]["parentProcessIds"] if p != pid]
        return specs

    def mark_available(rules, wid):
        rules = copy.deepcopy(rules)
        next(w for w in rules["workflows"] if w["id"] == wid)["cirroAvailability"] = "available"
        return rules

    fhir_deid = next(w["cirroProcess"] for w in rules["workflows"] if w["id"] == "deid_fhir")
    cases = [
        ("a data type's spec lacks a pipeline its files go to",
         rules, drop_child(committed, "rddc_ingest_fhir", fhir_deid), catalog,
         f"no Cirro link from rddc_ingest_fhir to {fhir_deid}"),
        ("a pipeline marked available is not in Cirro's catalog",
         mark_available(rules, "deid_fhir"), committed, catalog, "is marked available but is not in"),
        ("a spec edited by hand",
         rules, dict(committed, rddc_ingest_fhir=dict(committed["rddc_ingest_fhir"], isTenantWide=True)), catalog,
         "spec rddc_ingest_fhir.json is out of date"),
    ]
    print(f"\nSeeded broken specs and rules ({len(cases)}):")
    missed = 0
    for name, r, sp, cat, want in cases:
        got = link_errors(r, rel, links, sp, cat)
        ok = any(want in e for e in got)
        missed += not ok
        print(f"{'ok  ' if ok else 'FAIL'} {name}: {'caught' if ok else 'missed'}")
    return missed


if __name__ == "__main__":
    main()
