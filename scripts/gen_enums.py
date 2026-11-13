"""Regenerate the versioned FHIR and OMOP enums and rules in schema/data.yaml.

Usage: python scripts/gen_enums.py [--check] [--source VERSION_KEY=PATH_OR_URL ...] [FAMILY ...]

A family is a standard whose files use a value whose allowed set depends on the
standard's version:

  fhir  resourceType values. A FHIR file does not declare its version; its file set's
        conformsTo does, and the RDDC validator checks the value against it.
  omop  cdmTable values. Likewise: the OmopCdmInstance's conformsTo gives the version.

For each family the script generates, between BEGIN and END marker comments:

  <family>-<version key> one enum per version, with descriptions from its source
                         (FhirR4ResourceTypeEnum, OmopCdm54TableEnum)
  <family>-all           the union of all versions' values, the slot's range
                         (FhirResourceTypeEnum, OmopCdmTableEnum)

and, for a family whose files declare their version (none at present):

  <family>-versions      the version enum
  <family>-rules         one rule per version: if the file declares that version,
                         the value must be one of that version's values

LinkML's JSON Schema generator ignores enum inheritance and range narrowing in rules,
so the union and the rules list values explicitly. To support a new version, add it
to VERSIONS with its source and parser, add an empty <family>-<version key> enum with
markers to the schema, and run the script.

--source replaces a version's download URL with a local file or another URL. With
--check, nothing is written: the script exits 1 if the schema differs from what the
sources would generate. FAMILY selects families (default: all).
"""

import argparse
import csv
import io
import json
import os
import re
import sys
import urllib.request

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def quote(text):
    """Collapse whitespace; a JSON string is a valid YAML scalar and survives any punctuation."""
    return json.dumps(" ".join(text.split()), ensure_ascii=False)


# Approved wording edits to imported definitions; retain the remaining source text.
DESCRIPTION_EDITS = {
    'fhir-r4': {
        'ActivityDefinition': (
            'This resource allows for the definition of some activity to be performed',
            'Defines an activity',
        ),
        'AuditEvent': (
            'A record of an event made for purposes of maintaining a security log.',
            'An event record for a security log.',
        ),
        'BodyStructure': (
            'the necessary detail needed for the use case',
            'the detail required for the use case',
        ),
        'CarePlan': (
            'Describes the intention of how one or more practitioners intend to deliver care',
            'Describes how one or more practitioners plan to deliver care',
        ),
        'Communication': (
            'An occurrence of information being transmitted',
            'An instance of information exchange',
        ),
        'Composition': (
            'assembled together into a single logical package',
            'assembled into one logical package',
        ),
        'Encounter': (
            'for the purpose of providing healthcare service(s) or assessing the health status of a patient',
            "to provide healthcare or assess the patient's health",
        ),
        'Measure': (
            'The Measure resource provides the definition of a quality measure.',
            'Defines a quality measure.',
        ),
        'Organization': (
            'formed for the purpose of achieving some form of collective action',
            'formed to act collectively',
        ),
        'Practitioner': (
            'involved in the provisioning of healthcare',
            'involved in providing healthcare',
        ),
        'TestReport': (
            'A summary of information based on the results of executing a TestScript.',
            'A summary of TestScript execution results.',
        ),
    },
    'omop-cdm54': {
        'visit_detail': (
            'A good example of this would be',
            'Examples include',
        ),
        'location': (
            'represents a generic way to capture physical location or address information',
            'stores physical location or address information',
        ),
        'drug_era': (
            'is defined as a span of time when',
            'is a period when',
        ),
        'dose_era': (
            'is defined as a span of time when',
            'is a period when',
        ),
        'condition_era': (
            'is defined as a span of time when',
            'is a period when',
        ),
        'metadata': (
            'contains metadata information about a dataset',
            'contains metadata about a dataset',
        ),
        'concept_synonym': (
            ', providing users with a comprehensive view of how Concepts may be expressed or referenced',
            '',
        ),
    },
}


def edited_description(family, name, text):
    text = " ".join(text.split())
    edit = DESCRIPTION_EDITS[family].get(name)
    return text.replace(*edit) if edit else text


# --- source parsers: raw text -> list of (value, YAML lines for its details) --------

def fhir_r4(raw):
    code_system = json.loads(raw)
    found = (code_system.get("url"), code_system.get("version"))
    if found != ("http://hl7.org/fhir/resource-types", "4.0.1"):
        sys.exit(f"fhir-r4: expected the resource-types code system, version 4.0.1; got {found}")
    stack, concepts = list(code_system.get("concept", [])), []
    while stack:
        concept = stack.pop()
        concepts.append(concept)
        stack.extend(concept.get("concept", []))
    return [
        (c["code"], [f"meaning: fhir:{c['code']}", f"description: {quote(edited_description('fhir-r4', c['code'], c.get('definition', '')))}"])
        for c in sorted(concepts, key=lambda c: c["code"])
        if c["code"] not in {"Resource", "DomainResource"}  # abstract: no instance has them
    ]


def omop_cdm54(raw):
    rows = list(csv.DictReader(io.StringIO(raw)))
    if not rows or not {"cdmTableName", "schema", "tableDescription"} <= set(rows[0]):
        sys.exit("omop-cdm54: expected the OMOP CDM Table_Level CSV (cdmTableName, schema, tableDescription)")
    unknown = {r["schema"] for r in rows} - {"CDM", "VOCAB", "RESULTS"}
    if unknown:
        sys.exit(f"omop-cdm54: unknown schema values {sorted(unknown)}")
    # Keep the source's order: it groups tables the way the CDM documentation does.
    return [
        (r["cdmTableName"], [f"description: {quote(edited_description('omop-cdm54', r['cdmTableName'], r['tableDescription']))}",
                             "annotations:", f"  cdm_schema: {r['schema']}"])
        for r in rows
    ]


# --- families and their versions ----------------------------------------------------

FAMILIES = {
    "fhir": {
        "version_slot": None,  # the file set declares the version
        "value_slot": "resourceType",
        "sort_union": True,
        "versions": [
            # (version value, version key, label, source, parser)
            ("4.0.1", "r4", "FHIR R4", "https://hl7.org/fhir/R4/codesystem-resource-types.json", fhir_r4),
        ],
    },
    "omop": {
        "version_slot": None,  # the file set declares the version
        "value_slot": "cdmTable",
        "sort_union": False,
        "versions": [
            ("5.4", "cdm54", "OMOP CDM 5.4",
             "https://raw.githubusercontent.com/OHDSI/CommonDataModel/v5.4.3/inst/csv/OMOP_CDMv5.4_Table_Level.csv",
             omop_cdm54),
        ],
    },
}


def scalar(value):
    """A YAML scalar for a code: bare when YAML reads it as a string, quoted otherwise (e.g. 5.4)."""
    return value if re.fullmatch(r"[A-Za-z_][A-Za-z0-9_]*", value) else json.dumps(value)


def fetch(source):
    if source.startswith(("http://", "https://")):
        with urllib.request.urlopen(source, timeout=60) as response:
            return response.read().decode("utf-8")
    with open(source, encoding="utf-8") as f:
        return f.read()


def render_values(indent, entries):
    """Permissible values: entries are (value, detail lines)."""
    pad = " " * indent
    out = []
    for value, details in entries:
        if details:
            out.append(f"{pad}{scalar(value)}:\n" + "".join(f"{pad}  {d}\n" for d in details))
        else:
            out.append(f"{pad}{scalar(value)}:\n")
    return "".join(out)


def render_rules(indent, family, per_version):
    pad = " " * indent
    out = []
    for (version, _, label, _, _), values in per_version:
        out.append(
            f"{pad}- description: {quote(f'A file that declares {label} uses its {family['value_slot']} values.')}\n"
            f"{pad}  preconditions:\n{pad}    slot_conditions:\n"
            f"{pad}      {family['version_slot']}:\n{pad}        equals_string: {scalar(version)}\n"
            f"{pad}  postconditions:\n{pad}    slot_conditions:\n"
            f"{pad}      {family['value_slot']}:\n{pad}        equals_string_in:\n"
            + "".join(f"{pad}        - {scalar(v)}\n" for v, _ in values)
        )
    return "".join(out)


def replace(text, region, render):
    """Replace the lines between the region's markers; render(indent) gives the new lines."""
    pattern = re.compile(
        rf"^( *)# BEGIN generated by scripts/gen_enums\.py {re.escape(region)}\n(.*?)^\1# END generated by scripts/gen_enums\.py {re.escape(region)}\n",
        re.M | re.S)
    matches = list(pattern.finditer(text))
    if len(matches) != 1:
        sys.exit(f"{region}: expected one BEGIN/END marker pair in the schema, found {len(matches)}")
    m = matches[0]
    indent = len(m.group(1))
    new = render(indent)
    block = f"{m.group(1)}# BEGIN generated by scripts/gen_enums.py {region}\n{new}{m.group(1)}# END generated by scripts/gen_enums.py {region}\n"
    return text[:m.start()] + block + text[m.end():], m.group(2) != new


def main():
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0],
                                     formatter_class=argparse.RawDescriptionHelpFormatter, epilog=__doc__)
    parser.add_argument("families", nargs="*", metavar="FAMILY", help=f"families to regenerate: {', '.join(FAMILIES)}")
    parser.add_argument("--schema", default=os.path.join(ROOT, "schema", "data.yaml"))
    parser.add_argument("--source", action="append", default=[], metavar="VERSION_KEY=PATH_OR_URL",
                        help="e.g. fhir-r4=/tmp/codesystem-resource-types.json")
    parser.add_argument("--check", action="store_true", help="report whether the schema is up to date; write nothing")
    args = parser.parse_args()

    names = args.families or list(FAMILIES)
    for name in names:
        if name not in FAMILIES:
            parser.error(f"unknown family {name}; choose from {', '.join(FAMILIES)}")
    sources = {f"{name}-{key}": src for name, fam in FAMILIES.items() for _, key, _, src, _ in fam["versions"]}
    for item in args.source:
        key, _, source = item.partition("=")
        if key not in sources or not source:
            parser.error(f"--source needs VERSION_KEY=PATH_OR_URL with VERSION_KEY in {', '.join(sources)}")
        sources[key] = source

    text = original = open(args.schema, encoding="utf-8").read()
    stale = []
    for name in names:
        family = FAMILIES[name]
        per_version = [(v, v[4](fetch(sources[f"{name}-{v[1]}"]))) for v in family["versions"]]

        union, seen = [], set()
        for _, values in per_version:
            for value, _ in values:
                if value not in seen:
                    seen.add(value)
                    union.append((value, []))
        if family["sort_union"]:
            union.sort()

        regions = [(f"{name}-{v[1]}", lambda i, values=values: render_values(i, values)) for v, values in per_version]
        regions += [(f"{name}-all", lambda i: render_values(i, union))]
        if family["version_slot"]:
            regions += [(f"{name}-versions", lambda i: render_values(i, [(v[0], [f"description: {quote(v[2])}"]) for v, _ in per_version])),
                        (f"{name}-rules", lambda i: render_rules(i, family, per_version))]
        for region, render in regions:
            text, changed = replace(text, region, render)
            stale += [region] if changed else []
        counts = ", ".join(f"{v[2]}: {len(values)}" for v, values in per_version)
        print(f"{name}: {counts}; union: {len(union)}")

    if args.check:
        print("up to date" if not stale else f"OUT OF DATE: {', '.join(stale)}")
        sys.exit(1 if stale else 0)
    if text != original:
        with open(args.schema, "w", encoding="utf-8") as f:
            f.write(text)
        print(f"updated {', '.join(stale)}")


if __name__ == "__main__":
    main()
