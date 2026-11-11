"""Check a processing rule set: its names, and the verification properties.

Usage: python scripts/check_rules.py [RULES]

RULES defaults to rules/rules.yaml. The script

1. validates the rule set against schema/processing.yaml (class RuleSet);
2. checks that every class, file set class, flag, annotation, technique, interaction,
   sidecar field and source register field and value it names exists in the model
   release it pins (modelRelease), that every schema module in that release declares
   the same version, and that its own references (zones, workflows, properties,
   standards) resolve;
3. runs rules/engine.lp (clingo) over every kind of deposit, including every
   combination of the register values the rules read, and reports, with a route for
   each:
   - coverage: every deposit has exactly one target and a route to it;
   - obligations hold on every route, and no route enters a prohibited zone;
   - no route has a cycle;
   - withdraw and restrict reach every zone data can reach;
   and, as warnings, workflows that no deposit can run;
4. applies each mutation in MUTATIONS (a seeded broken rule) and checks that the
   expected violation is found.

Exits non-zero if the rule set fails, or a mutation is not caught.
"""

import copy
import multiprocessing
import os
import sys
import time
from collections import defaultdict

from linkml.validator import validate

import rules_engine as E

SCHEMA = os.path.join(E.ROOT, "schema", "processing.yaml")


def check(rules, rel, verbose=True):
    """Return the list of problems (names, then violations); print them if verbose."""
    def say(*a):
        if verbose:
            print(*a)

    report = validate(rules, SCHEMA, "RuleSet")
    problems = [f"schema: {r.message}" for r in report.results]
    problems += E.name_errors(rules, rel)
    if problems:
        for p in problems:
            say("FAIL", p)
        return problems
    t0 = time.time()
    deposits, profiles = E.verification_deposits(rules, rel)
    facts = E.catalog_facts(rules, rel) + "\n" + deposits
    found = E.by_name(E.solve(["engine.lp"], facts))
    say(f"{deposits.count('start(')} kinds of deposit in {len(profiles)} profiles ({time.time() - t0:.1f} s)")
    if verbose and found.get("violation"):
        # Solve again, showing the state graph, to explain each violation with a route.
        found = E.by_name(E.solve(["engine.lp"], facts + "\n#show step/4.\n#show st0/2."))
    starts = defaultdict(list)
    for p, st in found.get("st0", []):
        starts[p].append(st)
    steps = found.get("step", [])

    by_rule = defaultdict(list)
    for rule, p, state in found.get("violation", []):
        by_rule[rule].append((p, state))
    for rule in sorted(by_rule, key=str):
        cases = sorted(by_rule[rule], key=str)
        name = rule if isinstance(rule, str) else " ".join(str(x) for x in rule)
        problems.append(name)
        say(f"FAIL {name}: {len(cases)} state(s), e.g.")
        p, state = cases[0]
        start, path = E.example_route(p, state, steps, starts)
        say(f"       {E.describe_deposit(profiles[p], start, rules)}")
        say(f"       start  {E.state_text(start, rules)}")
        for w, s in path:
            say(f"       {w:<20} -> {E.state_text(s, rules)}")
    for interaction, zone in sorted(found.get("iviolation", []), key=str):
        name = f"interaction {interaction[1]} does not cover zone {zone}"
        problems.append(name)
        say("FAIL", name)
    for (w,) in sorted(found.get("unused", [])):
        say(f"warn workflow {w}: no deposit can run it")
    if not problems:
        say("ok   every deposit has one target and a route to it")
        say("ok   obligations and prohibitions hold on every route; no cycles")
        say("ok   withdraw and restrict cover every zone data can reach")
    return problems


def wf(rules, wid):
    return next(w for w in rules["workflows"] if w["id"] == wid)


def edit(fn):
    def mutate(rules):
        fn(rules)
        return rules
    return mutate


# Seeded broken rules, with a fragment of the violation each must produce.
def ingest(r):
    return wf(r, "ingest_files")["cirroIngestTypes"]


MUTATIONS = {
    "Cirro ingest: a data type that is not in the enum": (
        edit(lambda r: ingest(r)[0].update(dataType="paired_dna_seq")),
        "not a value of CirroDataTypeEnum"),
    "Cirro ingest: an INSDC platform token instead of the enum value": (
        edit(lambda r: ingest(r)[0].update(platforms=["OXFORD_NANOPORE"])),
        "sequencing platform 'OXFORD_NANOPORE' is not in release"),
    "pipelines: a pipeline in a repository the rule set does not list": (
        edit(lambda r: wf(r, "deid_fhir").update(pipelineRepository="clinicl")),
        "pipeline repository 'clinicl' is not in the rule set"),
    "pipelines: the two date masking workflows run one process from different code": (
        edit(lambda r: wf(r, "release_mask_year").update(pipelineName="mask_year")),
        "runs process-rddc-release-mask-0_0 like release_mask_shift, but with other code"),
    "Cirro ingest: no data type takes video": (
        edit(lambda r: ingest(r).remove(next(t for t in ingest(r) if t["dataType"] == "rddc_ingest_video"))),
        "no data type (without a technique or platform test) takes VideoFile"),
    "publish no longer requires masked dates": (
        edit(lambda r: wf(r, "publish")["consumes"]["noProperties"].remove("dates")),
        "obligation mask_before_release"),
    "the curation hold writes to the release": (
        edit(lambda r: wf(r, "curation_hold").update(writesTo="release")),
        "prohibition biometric_stays_in_intake"),
    "Cirro: a Cirro pipeline reads straight from the deposit": (
        edit(lambda r: wf(r, "fhir_to_omop")["readsFrom"].append("deposit")),
        "reads from zone deposit, which is not a Cirro environment (ingest first)"),
    "Cirro: a container writes into a Cirro environment": (
        edit(lambda r: wf(r, "publish").update(writesTo="normalized")),
        "a container writes to zone normalized, a Cirro environment"),
    "lane 4 accepts free text": (
        edit(lambda r: wf(r, "tabular_load")["consumes"]["noProperties"].remove("free_text")),
        "obligation text_deid_before_loading"),
    "lane 4 loads de-identified text that was not confirmed": (
        edit(lambda r: wf(r, "tabular_load")["consumes"]["noProperties"].remove("deid_unconfirmed")),
        "obligation confirm_deid_before_loading"),
    "the Comprehend Medical check is recorded as a process": (
        edit(lambda r: wf(r, "confirm_deid").update(kind="process")),
        "a service writes to zone deid_qc, a Cirro environment"),
    "table de-identification is recorded as a transform": (
        edit(lambda r: wf(r, "deid_tabular").update(kind="transform")),
        "obligation text_deid_before_loading"),
    "normalization: the VRS workflow does not produce VRS": (
        edit(lambda r: wf(r, "vcf_to_vrs").pop("producesStandard")),
        "no_route vrs"),
    "lane 2 takes FHIR free text": (
        edit(lambda r: wf(r, "fhir_to_omop")["consumes"]["noProperties"].remove("free_text")),
        "obligation text_deid_before_loading"),
    "sensor measures load without QC": (
        edit(lambda r: wf(r, "sensor_load")["consumes"]["noProperties"].remove("sensor_qc_pending")),
        "obligation sensor_qc_before_loading"),
    "no workflow turns sensor signals into measures": (
        edit(lambda r: r["workflows"].remove(wf(r, "sensor_to_measures"))),
        "no_route sensor"),
    "two targets claim FHIR at the same priority": (
        edit(lambda r: r["targets"].append(
            {"id": "fhir_hold", "when": {"classes": ["FhirFile"]}, "goalZone": "deid_qc", "priority": 1})),
        "target_conflict"),
    "withdraw does not reach the curation hold": (
        edit(lambda r: wf(r, "withdraw_subjects")["coversZones"].remove("curation")),
        "interaction withdraw does not cover zone curation"),
    "masking runs on data with nothing to mask": (
        edit(lambda r: wf(r, "release_mask_shift")["consumes"].pop("anyProperties")),
        "cycle"),
    "register: open publication ignores the access tier": (
        edit(lambda r: wf(r, "publish_open")["consumes"]["sourceFacts"].pop(0)),
        "prohibition only_open_tier_is_public"),
    "register: publish skips the expert determination": (
        edit(lambda r: wf(r, "publish")["consumes"]["noProperties"].remove("needs_expert_review")),
        "obligation expert_review_before_release"),
    "register: lane 2 takes a modality the source is not registered for": (
        edit(lambda r: wf(r, "fhir_to_omop")["consumes"]["noProperties"].remove("unregistered_modality")),
        "prohibition unregistered_stays_in_intake"),
    "register: a value that is not in the release": (
        edit(lambda r: wf(r, "publish_open")["consumes"]["sourceFacts"][0].update(anyOf=["Open"])),
        "'Open' is not a value of register field accessTier"),
    "a class name that is not in the release": (
        edit(lambda r: r["targets"][1]["when"].update(classes=["FhirNdjson"])),
        "data class 'FhirNdjson' is not in release"),
    "a property reads the synthetic flag": (
        edit(lambda r: r["properties"][0]["derivedFrom"].append({"source": "flag_true", "key": "synthetic"})),
        "seed rule 10"),
}


RULES, REL = None, None


def check_mutation(name):
    """(name, expect, caught, error). An exception counts as not caught, and is returned
    rather than raised: pool.imap would re-raise it in the parent, where a StopIteration
    would silently end the loop over results."""
    mutate, expect = MUTATIONS[name]
    try:
        problems = check(mutate(copy.deepcopy(RULES)), REL, verbose=False)
    except Exception as e:
        return name, expect, False, f"{type(e).__name__}: {e}"
    return name, expect, any(expect in p for p in problems), None


def main():
    global RULES, REL
    path = sys.argv[1] if len(sys.argv) > 1 else os.path.join(E.RULES_DIR, "rules.yaml")
    RULES = E.load_rules(path)
    REL = E.Release(RULES["modelRelease"])
    print(f"Rule set {RULES['id']} {RULES['version']}, pinned to {REL.tag}")
    if REL.note:
        print(f"note {REL.note}")
    failed = bool(check(RULES, REL))

    print(f"\nSeeded broken rules ({len(MUTATIONS)}):")
    # Each mutation is a full check; run them in parallel (forked workers share RULES, REL).
    with multiprocessing.get_context("fork").Pool() as pool:
        results = pool.map(check_mutation, MUTATIONS)
    for name, expect, caught, error in results:
        failed |= not caught
        detail = "caught" if caught else f"error {error}" if error else "not caught"
        print(f"{'ok  ' if caught else 'FAIL'} {name}: {detail} ({expect})")
    if len(results) != len(MUTATIONS):
        failed = True
        print(f"FAIL only {len(results)} of {len(MUTATIONS)} mutations ran")
    sys.exit(1 if failed else 0)


if __name__ == "__main__":
    main()
