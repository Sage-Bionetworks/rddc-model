"""Check the example documents against the generated schemas.

Usage: python scripts/check_examples.py

1. Every examples/*.json validates against its JSON Schema (sidecar, or source
   descriptor for source_descriptor*.json).
2. Each mutation of examples/deposit_fhir_omop.json in INVALID must fail.
3. If mlcroissant is importable, every sidecar example also passes Croissant
   validation (run with an interpreter that has it, e.g. CROISSANT_PY in the
   Makefile).
"""

import copy
import glob
import json
import os
import sys

import jsonschema

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
GEN = os.path.join(ROOT, "schema", "generated")


def validator(name):
    schema = json.load(open(os.path.join(GEN, name)))
    return jsonschema.validators.validator_for(schema)(schema)


def at(doc, path):
    for key in path[:-1]:
        doc = doc[key]
    return doc, path[-1]


def put(path, value):
    def mutate(doc):
        parent, key = at(doc, path)
        parent[key] = value
    return mutate


def drop(path):
    def mutate(doc):
        parent, key = at(doc, path)
        del parent[key]
    return mutate


def both(*mutations):
    def mutate(doc):
        for m in mutations:
            m(doc)
    return mutate


FHIR, OMOP_SET, OMOP_TABLE = ["distribution", 4], ["distribution", 1], ["distribution", 6]
INVALID = {
    "file @type is the subclass, not cr:FileObject": put(FHIR + ["@type"], "rddc:FhirNdjsonFile"),
    "additionalType missing": drop(FHIR + ["additionalType"]),
    "unknown additionalType": put(FHIR + ["additionalType"], "rddc:NdjsonFile"),
    "FHIR NDJSON without resourceType": drop(FHIR + ["resourceType"]),
    "FHIR NDJSON with an OMOP field": put(FHIR + ["cdmTable"], "person"),
    "FHIR NDJSON with text/csv": put(FHIR + ["encodingFormat"], "text/csv"),
    "FHIR version on a FHIR file": put(FHIR + ["fhirVersion"], "4.0.1"),
    "resourceType not in FHIR R4": put(FHIR + ["resourceType"], "ActorDefinition"),
    "implementation guides on a FHIR file": put(FHIR + ["implementationGuides"], ["hl7.fhir.us.core#6.1.0"]),
    "contentSize without unit": put(FHIR + ["contentSize"], "1010"),
    "sha256 too short": put(FHIR + ["sha256"], "abc"),
    "unknown compression": put(FHIR + ["compression"], "rar"),
    "file @id not a UUID URN": put(FHIR + ["@id"], "patient-file"),
    "synthetic set per file": put(FHIR + ["sensitivity"], {"synthetic": True}),
    "header without directIdentifiersRemoved": drop(["sensitivity", "directIdentifiersRemoved"]),
    "removed sidecarType": put(["sidecarType"], "deposit"),
    "removed wasGeneratedBy": put(FHIR + ["wasGeneratedBy"], {"@type": "prov:Activity", "name": "x"}),
    "no conformsTo": drop(["conformsTo"]),
    "temporalCoverage not an ISO 8601 interval": put(["temporalCoverage"], "2019-2026"),
    "temporalCoverage with a time of day": put(["temporalCoverage"], "2024-03-01T10:00/2024-03-02"),
    "temporalCoverage on a file set with two open ends": put(OMOP_SET + ["temporalCoverage"], "../.."),
    "url not an s3 prefix": put(["url"], "https://example.org/batch"),
    "withdraw without noticeRef": put(["interaction"], "withdraw"),
    "plan label upsert": put(["interaction"], "upsert"),
    "removed sidecar supersedes": put(["supersedes"], "urn:uuid:00000001-0000-4000-8000-000000000001"),
    "removed supersedesBatch": put(["supersedesBatch"], "2026-10-b00"),
    "removed retiredFiles": put(["retiredFiles"], ["urn:uuid:00000001-0000-4000-8000-000000000001"]),
    "removed correction header": both(
        put(["supersedes"], "urn:uuid:00000001-0000-4000-8000-000000000001"),
        put(["supersedesBatch"], "2026-10-b00"),
        put(["retiredFiles"], ["urn:uuid:0000000a-0000-4000-8000-00000000000a"]),
    ),
    "removed file supersedes": put(FHIR + ["supersedes"], "urn:uuid:0000000a-0000-4000-8000-00000000000a"),
    "no subject table": drop(["subjects"]),
    "subject table in a companion file": both(drop(["subjects"]), put(["subjectsFile"], {"@id": "urn:uuid:00000063-0000-4000-8000-000000000063"})),
    "subject without idSystem": drop(["subjects", 0, "idSystem"]),
    "Patient.identifier without system URI": put(["subjects", 0, "idSystem"], "fhir_patient_identifier"),
    "OMOP table not in CDM 5.4": put(OMOP_TABLE + ["cdmTable"], "patient"),
    "OMOP CDM version on a table file": put(OMOP_TABLE + ["omopCdmVersion"], "5.4"),
    "OMOP CDM version in cdmSource": put(OMOP_SET + ["cdmSource", "cdmVersion"], "5.4"),
    "OMOP set without cdmSource": drop(OMOP_SET + ["cdmSource"]),
    "OMOP set without conformsTo": drop(OMOP_SET + ["conformsTo"]),
    "file set with neither hasPart nor includes": both(drop(OMOP_SET + ["hasPart"]), drop(OMOP_SET + ["includes"])),
    "file set @type cr:FileObject": put(OMOP_SET + ["@type"], "cr:FileObject"),
    "field source with no file": drop(["recordSet", 0, "field", 0, "source", "fileObject"]),
    "extension key not namespaced": put(["additionalProperty"], [{"propertyID": "cohort", "value": "x"}]),
    "unknown property": put(["batchName"], "x"),
}


def main():
    sidecar, descriptor = validator("rddc_sidecar.schema.json"), validator("rddc_source_descriptor.schema.json")
    failures = 0
    examples = sorted(glob.glob(os.path.join(ROOT, "examples", "*.json")))
    for path in examples:
        v = descriptor if os.path.basename(path).startswith("source_descriptor") else sidecar
        errors = list(v.iter_errors(json.load(open(path))))
        failures += bool(errors)
        print(f"{'ok  ' if not errors else 'FAIL'} valid    {os.path.basename(path)}")
        for e in errors[:3]:
            print(f"       {e.json_path}: {e.message[:200]}")

    base = json.load(open(os.path.join(ROOT, "examples", "deposit_fhir_omop.json")))
    for name, mutate in INVALID.items():
        doc = copy.deepcopy(base)
        mutate(doc)
        rejected = not sidecar.is_valid(doc)
        failures += not rejected
        print(f"{'ok  ' if rejected else 'FAIL'} invalid  {name}")

    try:
        import logging
        import mlcroissant as mlc
    except ImportError:
        print("skip croissant: mlcroissant not installed")
    else:
        logging.disable(logging.WARNING)
        for path in examples:
            if os.path.basename(path).startswith("source_descriptor"):
                continue
            try:
                md = mlc.Dataset(jsonld=path).metadata
                print(f"ok   croissant {os.path.basename(path)} "
                      f"({len(md.distribution)} distribution, {len(md.ctx.issues.warnings)} warnings)")
            except Exception as e:  # mlcroissant raises ValidationError with all issues
                failures += 1
                print(f"FAIL croissant {os.path.basename(path)}: {str(e)[:500]}")

    print(f"\n{failures} failure(s)")
    sys.exit(1 if failures else 0)


if __name__ == "__main__":
    main()
