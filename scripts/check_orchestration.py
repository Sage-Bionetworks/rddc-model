"""Check the orchestrator on example sidecars and batch states.

Usage: python scripts/check_orchestration.py

1. For each sidecar in examples/, the first plan equals the committed
   examples/plans/<name>.plan.json.
2. Each route scenario (a change to examples/deposit_fhir_omop.json or to the source
   register) runs to the end with a stub dispatcher, and every file takes the expected
   route; or orchestration fails with the expected error.
3. Each state scenario (what the dispatcher reports: a failure, a step still running,
   residual free text, a step that should not have run) gives the expected statuses.
4. A ready step carries input locations, an output location and parameters resolved
   from the sidecar and the source register, and orchestration is repeatable.

Exits non-zero on any failure. Regenerate the committed plans with
python scripts/orchestrate.py examples/<name>.json --register examples/registers/source_register.json \\
    -o examples/plans/<name>.plan.json
"""

import copy
import glob
import json
import os
import sys

import orchestrate as O
import rules_engine as E

from linkml.validator import validate

EXAMPLES = os.path.join(E.ROOT, "examples")
REGISTER_PATH = os.path.join(EXAMPLES, "registers", "source_register.json")
REGISTER = json.load(open(REGISTER_PATH))
BASE = json.load(open(os.path.join(EXAMPLES, "deposit_fhir_omop.json")))
FILES = {"Patient": "urn:uuid:0000000a-0000-4000-8000-00000000000a",
         "Observation": "urn:uuid:0000000b-0000-4000-8000-00000000000b",
         "person": "urn:uuid:00000014-0000-4000-8000-000000000014",
         "patients": "urn:uuid:0000001e-0000-4000-8000-00000000001e",
         "visits": "urn:uuid:0000001f-0000-4000-8000-00000000001f"}


def file_obj(doc, key):
    return next(d for d in doc["distribution"] if d["@id"] == FILES[key])


def sidecar(fn=None):
    doc = copy.deepcopy(BASE)
    if fn:
        fn(doc)
    return doc


def register(fn=None):
    reg = copy.deepcopy(REGISTER)
    if fn:
        fn(reg["sources"][0])
    return reg


def free_text_visits(doc):
    file_obj(doc, "visits")["sensitivity"] = {"containsFreeText": True}


def sensor_visits(doc):
    file_obj(doc, "visits").update(additionalType="rddc:SensorSignalFile", measurementTechnique=["accelerometry"],
                                   encodingFormat="application/octet-stream")


def run(doc, reg, report=None, rounds=10):
    """Orchestrate and stub-dispatch until nothing is ready; return the last plan."""
    rules = E.load_rules()
    plan = O.orchestrate(doc, rules, reg)
    for _ in range(rounds):
        if not any(True for _ in O.ready_steps(plan)):
            break
        plan = O.orchestrate(doc, rules, reg, O.stub_dispatch(plan, report))
    return plan


def routes(plan):
    return {f: [s["workflow"] for s in g["steps"]] for g in plan["groups"] for f in g["files"]}


def group_of(plan, key):
    return next(g for g in plan["groups"] if FILES[key] in g["files"])


# name: (sidecar, register, {file key: expected route} or fragment of the expected error)
ROUTES = {
    # Patient.ndjson has no free text, but moves with Observation.ndjson (same file set
    # and target), so FHIR-to-OMOP runs once on the whole export.
    "FHIR free text is de-identified and confirmed before lane 2, with its whole file set": (
        sidecar(), register(),
        {"Observation": ["ingest_files", "deid_fhir", "confirm_deid", "fhir_to_omop"],
         "Patient": ["ingest_files", "deid_fhir", "confirm_deid", "fhir_to_omop"]}),
    "free text in one table is de-identified before lane 4, with its whole file set": (
        sidecar(free_text_visits), register(),
        {"visits": ["ingest_files", "deid_tabular", "confirm_deid", "tabular_load"],
         "patients": ["ingest_files", "deid_tabular", "confirm_deid", "tabular_load"],
         "Patient": ["ingest_files", "deid_fhir", "confirm_deid", "fhir_to_omop"]}),
    # The seed rules require de-identification only before release, so direct
    # identifiers reach the normalized store. To confirm with the team.
    "unconfirmed direct identifiers do not change the lanes": (
        sidecar(lambda d: d["sensitivity"].update(directIdentifiersRemoved=False)), register(),
        {"visits": ["ingest_files", "tabular_load"],
         "Patient": ["ingest_files", "deid_fhir", "confirm_deid", "fhir_to_omop"]}),
    "a FHIR file with biometric identifiers is held for a curator": (
        sidecar(lambda d: file_obj(d, "Patient").update(sensitivity={"containsBiometricIdentifiers": True})),
        register(), {"Patient": ["curation_hold"],
                     "Observation": ["ingest_files", "deid_fhir", "confirm_deid", "fhir_to_omop"]}),
    "a missing flag counts as present": (
        sidecar(lambda d: d["sensitivity"].pop("containsBiometricIdentifiers")), register(),
        {"Patient": ["curation_hold"], "patients": ["curation_hold"]}),
    "register: sensor signals from a source registered for wearables become measures": (
        sidecar(sensor_visits), register(lambda s: s["modalities"].append("wearable")),
        {"visits": ["ingest_files", "qc_sensory", "sensor_to_measures", "sensor_load"]}),
    "register: sensor signals from a source not registered for wearables are held": (
        sidecar(sensor_visits), register(), {"visits": ["curation_hold"], "patients": ["ingest_files", "tabular_load"]}),
    "register: consent elements are recorded in GOVERN; the file stays in INTAKE": (
        sidecar(lambda d: file_obj(d, "visits").update(additionalType="rddc:ConsentFile")),
        register(lambda s: s["modalities"].append("consent")),
        {"visits": ["ingest_files", "record_consent"], "patients": ["ingest_files", "tabular_load"]}),
    "normalization: a VCF is represented in GA4GH VRS in the normalized store": (
        sidecar(lambda d: file_obj(d, "visits").update(additionalType="rddc:VariantFile", measurementTechnique="wgs",
                                                        referenceGenome="GRCh38", encodingFormat="text/plain")),
        register(lambda s: s["modalities"].append("genomics")),
        {"visits": ["ingest_files", "vcf_to_vrs"]}),
    "audio and video go to INTAKE's de-id/QC environment, not to a curator": (
        sidecar(lambda d: (file_obj(d, "visits").update(additionalType="rddc:AudioFile", encodingFormat="audio/wav"),
                           file_obj(d, "patients").update(additionalType="rddc:VideoFile", encodingFormat="video/mp4"))),
        register(lambda s: s["modalities"].extend(["audio", "video"])),
        {"visits": ["ingest_files"], "patients": ["ingest_files"]}),
    "register: a source that is not in the register is refused": (
        sidecar(lambda d: d.update(sourceId="src-unknown")), register(), "is not in the source register"),
    "a sidecar for another release is refused": (
        sidecar(lambda d: d["conformsTo"].__setitem__(1, "https://w3id.org/rddc/sidecar/0.2.0")), register(),
        "the rule set pins v0.1.0"),
}


def residual_free_text(group, step):
    # The text de-identification run reports that free text is left in visits.
    if step["workflow"].startswith("deid_"):
        return [{"file": f, "properties": ["free_text"]} for f in group["files"]]
    return None


def plan_with(doc, status_of, rounds=10):
    """Dispatch until nothing is ready, giving each ready step a status: {workflow:
    status}, default succeeded (with the stub's results)."""
    rules = E.load_rules()
    plan = O.orchestrate(doc, rules, REGISTER)
    for _ in range(rounds):
        ready = list(O.ready_steps(plan))
        if not ready:
            break
        plan = O.stub_dispatch(plan)
        for g in plan["groups"]:
            for s in g["steps"]:
                if s.get("dispatchId") in {r["dispatchId"] for _, r in ready} and s["workflow"] in status_of:
                    s["status"] = status_of[s["workflow"]]
                    s.pop("results", None)
        plan = O.orchestrate(doc, rules, REGISTER, plan)
    return plan


def made_up_history(doc, workflows):
    """A state in which visits went through the given workflows, all succeeded."""
    rules = E.load_rules()
    plan = O.orchestrate(doc, rules, REGISTER)
    g = group_of(plan, "visits")
    entry = E.register_entry(REGISTER, "src-ta2-01")
    g["steps"] = [O.new_step(rules, w, "pending", doc, None, entry) for w in workflows]
    for i, st in enumerate(g["steps"]):
        st.update(status="succeeded", dispatchId=f"made-up-{i}")
    return O.orchestrate(doc, rules, REGISTER, plan)


def phi_found(group, step):
    # Comprehend Medical finds PHI in visits after de-identification.
    if step["workflow"] == "confirm_deid":
        return [{"file": f, "properties": ["free_text", "direct_identifiers"]} for f in group["files"]]
    return None


def state_checks():
    """(name, ok, detail) for each state scenario."""
    out = []
    p = run(sidecar(free_text_visits), REGISTER, phi_found)
    g = group_of(p, "visits")
    out.append(("PHI found by the confirmation check blocks its file set, not the batch",
                p["status"] == "blocked" and "no route" in " ".join(g.get("problems", []))
                and routes(p)[FILES["visits"]] == ["ingest_files", "deid_tabular", "confirm_deid"]
                and routes(p)[FILES["patients"]] == ["ingest_files", "deid_tabular", "confirm_deid"]
                and group_of(p, "Patient")["steps"][-1]["status"] == "succeeded",
                f"status {p['status']}, visits {routes(p)[FILES['visits']]}"))
    p = run(sidecar(free_text_visits), REGISTER, residual_free_text)
    g = group_of(p, "visits")
    out.append(("residual free text after de-identification blocks its file set, not the batch",
                p["status"] == "blocked" and "no route" in " ".join(g.get("problems", []))
                and routes(p)[FILES["patients"]] == ["ingest_files", "deid_tabular"]
                and group_of(p, "Patient")["steps"][-1]["status"] == "succeeded",
                f"status {p['status']}, visits {routes(p)[FILES['visits']]}"))
    p = plan_with(sidecar(), {"fhir_to_omop": "failed"})
    g = group_of(p, "Patient")
    out.append(("a failed step blocks its files; the rest finish",
                p["status"] == "blocked" and "failed" in " ".join(g.get("problems", []))
                and all(s["status"] == "succeeded" for s in group_of(p, "patients")["steps"]),
                f"status {p['status']}"))
    p = plan_with(sidecar(free_text_visits), {"deid_tabular": "running"})
    steps = [s["status"] for s in group_of(p, "visits")["steps"]]
    out.append(("files with a step running wait for it",
                p["status"] == "in_progress" and steps == ["succeeded", "running", "pending", "pending"],
                f"visits steps {steps}"))
    p = made_up_history(sidecar(free_text_visits), ["ingest_files", "deid_tabular", "deid_tabular"])
    out.append(("a step run twice on a file (a retry) stops the batch",
                p["status"] == "stopped" and any("repeated deid_tabular" in x for x in p.get("problems", [])),
                f"status {p['status']}, problems {p.get('problems')}"))
    p = made_up_history(sidecar(free_text_visits), ["ingest_files", "tabular_load"])
    out.append(("a step the rules do not allow (lane 4 on free text) stops the batch",
                p["status"] == "stopped" and any("cannot_run tabular_load" in x for x in p.get("problems", [])),
                f"status {p['status']}, problems {p.get('problems')}"))
    return out


def dispatch_checks():
    out = []
    rules = E.load_rules()
    doc = sidecar(free_text_visits)
    p1 = O.orchestrate(doc, rules, REGISTER)
    ingest = group_of(p1, "visits")["steps"][0]
    deposit = "s3://rddc-deposit-ta2/src-ta2-01/2026-10-b01/registry/visits.csv"
    out.append(("Cirro: an ingest uploads the deposited files into the de-id/QC environment",
                ingest["runner"] == "cirro" and ingest["cirroExecutor"] == "INGEST"
                and ingest["cirroEnvironment"] == "provisional-rddc-intake"
                and ingest["inputs"] == [{"file": FILES["patients"], "location": deposit.replace("visits", "patients")},
                                         {"file": FILES["visits"], "location": deposit}]
                and "outputLocation" not in ingest and "sourceDatasets" not in ingest,
                json.dumps(ingest)))
    p2 = O.orchestrate(doc, rules, REGISTER, O.stub_dispatch(p1))
    deid = group_of(p2, "visits")["steps"][1]
    ds = f"stub-dataset-{ingest['dispatchId']}"
    params = {x["id"]: x["value"] for x in deid.get("parameters", [])}
    out.append(("Cirro: an analysis reads its inputs' datasets, with parameters from the register",
                deid["workflow"] == "deid_tabular" and deid["status"] == "ready"
                and deid["cirroProcess"] == "process-rddc-provisional-tabular-deid-0_0"
                and deid["sourceDatasets"] == [ds] and deid["inputs"][0]["dataset"] == ds
                and params == {"deid_class": "safe_harbor"},
                json.dumps(deid)))
    p3 = O.orchestrate(doc, rules, REGISTER, O.stub_dispatch(p2))
    check = group_of(p3, "visits")["steps"][2]
    params = {x["id"]: x["value"] for x in check.get("parameters", [])}
    out.append(("a service step (Comprehend Medical) reads the de-identified dataset and writes its report",
                check["workflow"] == "confirm_deid" and check["status"] == "ready" and check["runner"] == "service"
                and check["pipeline"] == "aws:comprehendmedical:StartPHIDetectionJob"
                and check["inputs"][0]["location"].startswith("s3://provisional-rddc-intake/datasets/stub-dataset-deid_tabular-")
                and params["output_s3_uri"] == f"s3://provisional-rddc-deid-reports/src-ta2-01/2026-10-b01/{check['dispatchId']}/"
                and params["language_code"] == "en"
                and "outputLocation" not in check and "cirroEnvironment" not in check,
                json.dumps(check)))
    out.append(("orchestrating the same state again gives the same plan",
                O.orchestrate(doc, rules, REGISTER, O.stub_dispatch(p1)) == p2, ""))
    p = run(sidecar(lambda d: file_obj(d, "Patient").update(sensitivity={"containsBiometricIdentifiers": True})),
            REGISTER)
    hold = group_of(p, "Patient")["steps"][0]
    out.append(("a service step gets an output location from its zone's template",
                hold["runner"] == "service"
                and hold["outputLocation"].startswith("s3://provisional-rddc-curation/src-ta2-01/2026-10-b01/curation_hold-"),
                json.dumps(hold)))
    return out


def main():
    rules = E.load_rules()
    failed = False

    def report(ok, name, detail=""):
        nonlocal failed
        failed |= not ok
        print(f"{'ok  ' if ok else 'FAIL'} {name}{': ' + detail if detail and not ok else ''}")

    report(not validate(REGISTER, os.path.join(E.ROOT, "schema", "processing.yaml"), "SourceRegister").results,
           "the example source register validates")

    print("\nCommitted first plans:")
    for path in sorted(glob.glob(os.path.join(EXAMPLES, "*.json"))):
        name = os.path.basename(path)[:-5]
        if name.startswith("source_descriptor"):
            continue
        plan_path = os.path.join(EXAMPLES, "plans", name + ".plan.json")
        derived = O.orchestrate(json.load(open(path)), rules, REGISTER)
        committed = json.load(open(plan_path)) if os.path.exists(plan_path) else None
        report(committed == derived, name, "missing or out of date; regenerate it")

    print("\nRoutes, run to the end:")
    for name, (doc, reg, expect) in ROUTES.items():
        try:
            plan = run(doc, reg)
        except O.OrchestrationError as e:
            report(isinstance(expect, str) and expect in str(e), name, str(e))
            continue
        if isinstance(expect, str):
            report(False, name, f"expected an error: {expect}")
            continue
        got = routes(plan)
        wrong = {k: got.get(FILES[k]) for k, v in expect.items() if got.get(FILES[k]) != v}
        report(not wrong and plan["status"] in ("complete", "blocked"), name,
               "; ".join(f"{k}: got {v}" for k, v in wrong.items()) or f"status {plan['status']}")

    print("\nSite explorer agrees with the orchestrator:")
    for name, (doc, reg, expect) in ROUTES.items():
        if isinstance(expect, str):
            continue
        plan = run(doc, reg)
        rel = E.Release(rules["modelRelease"])
        files = E.sidecar_files(doc, E.register_entry(reg, doc["sourceId"]), rules, rel)
        explained = E.deposit_routes(rules, rel, [(f["profile"], f["class"], f["standard"], f["mask"]) for f in files])
        got = routes(plan)
        # The site explains one file. Files of a file set with the same target move
        # together, so within such a group every file gets the same route, and it is the
        # site's route for at least one of them (the one that needs the most).
        groups = {}
        for f, r in zip(files, explained):
            groups.setdefault((f["fileSet"] or f["id"], r["target"]), []).append((f, [w for w, _ in r["path"] or []], r))
        wrong = []
        for members in groups.values():
            shared = {tuple(got.get(f["id"]) or []) for f, _, _ in members}
            own = [tuple(p) for _, p, _ in members]
            if len(shared) != 1 or next(iter(shared)) not in own or any(r["ambiguous"] for _, _, r in members):
                wrong.append(f"{[f['id'][-4:] for f, _, _ in members]}: site {own}, orchestrator {sorted(shared)}")
        report(not wrong, name, "; ".join(wrong))

    print("\nBatch states:")
    for name, ok, detail in state_checks():
        report(ok, name, detail)

    print("\nDispatch:")
    for name, ok, detail in dispatch_checks():
        report(ok, name, detail)
    sys.exit(1 if failed else 0)


if __name__ == "__main__":
    main()
