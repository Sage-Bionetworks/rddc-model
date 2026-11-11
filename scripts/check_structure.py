"""Check the class annotations on the data file classes.

Usage: python scripts/check_structure.py [SCHEMA]

SCHEMA defaults to schema/data.yaml. LinkML does not validate annotation values,
so this script does. Exits non-zero if any concrete DataFile subclass:

- has no "structure" annotation, or an unknown value;
- has no "modality" annotation, or a value that is not in ModalityEnum;
- has a "biometric", "identifying" or "embedsFiles" annotation other than "true",
  or is a subclass of a class with one and does not repeat it;
- has both: "biometric" implies "identifying", so a biometric class leaves it out;
- has an "rai:dataCollectionType" annotation that is not one of the Croissant
  Responsible AI recommended values (the annotation is optional);
- has a sensitivity flag annotation (containsDates, containsZipCodes,
  containsFreeText, containsBiometricIdentifiers) other than "always", "n/a" or
  "false", or annotates containsBiometricIdentifiers while being biometric;
- fixes a flag ("always" or "n/a", or biometric) but its sensitivity range still
  has that flag, or lacks a flag it does not fix;
- names a "fileSetClass" that is not a concrete FileSet subclass of the sidecar
  module (schema/rddc_sidecar.yaml next to SCHEMA, when present).
"""

import os
import sys

from linkml_runtime.utils.schemaview import SchemaView

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
STRUCTURES = {"structured", "unstructured", "mixed"}
TRUE = {"true"}
FLAGS = ("containsDates", "containsZipCodes", "containsFreeText", "containsBiometricIdentifiers")
FLAG_VALUES = {"always", "n/a", "false"}
# Recommended values of rai:dataCollectionType (Croissant RAI vocabulary, croissant_rai.ttl).
COLLECTION_TYPES = {
    "Surveys", "Secondary Data analysis", "Physical data collection", "Direct measurement",
    "Document analysis", "Manual Human Curator", "Software Collection", "Experiments",
    "Web Scraping", "Web API", "Focus groups", "Self-reporting", "Customer feedback data",
    "User-generated content data", "Passive Data Collection", "Others",
}


def value(cls, key):
    ann = cls.annotations.get(key)
    return ann.value if ann is not None else None


def file_set_classes(path):
    """Concrete FileSet subclasses of the sidecar module next to the data module, if any."""
    sidecar = os.path.join(os.path.dirname(os.path.abspath(path)), "rddc_sidecar.yaml")
    if not os.path.exists(sidecar):
        return None
    sv = SchemaView(sidecar)
    return {c for c in sv.class_descendants("FileSet", reflexive=False) if not sv.get_class(c).abstract}


def check_class(sv, name, modalities, set_classes):
    cls = sv.get_class(name)
    problems = []
    structure, modality, biometric, identifying, embeds, collection, set_class = (
        value(cls, k) for k in ("structure", "modality", "biometric", "identifying", "embedsFiles",
                                "rai:dataCollectionType", "fileSetClass"))
    ancestors = [sv.get_class(a) for a in sv.class_ancestors(name, reflexive=False)]
    if structure not in STRUCTURES:
        problems.append(f"structure is {structure!r}")
    if modality not in modalities:
        problems.append(f"modality is {modality!r}")
    for key, val in (("biometric", biometric), ("identifying", identifying), ("embedsFiles", embeds)):
        if val is not None and val not in TRUE:
            problems.append(f"{key} is {val!r}, not \"true\"")
        # A subclass of a biometric, identifying or embedding class is one too, so it must say so.
        if val is None and any(value(a, key) is not None for a in ancestors):
            problems.append(f"inherits {key} but does not repeat it")
    if biometric is not None and identifying is not None:
        problems.append("biometric implies identifying; drop the identifying annotation")
    if collection is not None and collection not in COLLECTION_TYPES:
        problems.append(f"rai:dataCollectionType is {collection!r}")
    if set_class is not None and set_classes is not None and set_class not in set_classes:
        problems.append(f"fileSetClass {set_class} is not a concrete FileSet class")
    # Flag annotations, and the sensitivity range that must match the fixed ones.
    fixed = set()
    for flag in FLAGS:
        val = value(cls, flag)
        if val is None:
            continue
        if val not in FLAG_VALUES:
            problems.append(f"{flag} is {val!r}, not always, n/a or false")
        if flag == "containsBiometricIdentifiers" and biometric is not None:
            problems.append("a biometric class does not annotate containsBiometricIdentifiers")
        if val in ("always", "n/a"):
            fixed.add(flag)
    if biometric is not None:
        fixed.add("containsBiometricIdentifiers")
    sensitivity = next(s for s in sv.class_induced_slots(name) if s.name == "sensitivity")
    in_range = {s.name for s in sv.class_induced_slots(sensitivity.range)} & set(FLAGS)
    for flag in sorted(fixed & in_range):
        problems.append(f"fixes {flag} but its sensitivity range {sensitivity.range} still has it")
    for flag in sorted(set(FLAGS) - in_range - fixed):
        problems.append(f"sensitivity range {sensitivity.range} lacks {flag}, which the class does not fix")
    summary = f"{structure}, {modality}"
    for key, val in (("biometric", biometric), ("identifying", identifying), ("embedsFiles", embeds),
                     ("collected by", collection), ("in", set_class)):
        summary += f", {key}: {val}" if val is not None else ""
    flags = ", ".join(f"{f}={value(cls, f)}" for f in FLAGS if value(cls, f) is not None)
    summary += f" [{flags}]" if flags else ""
    return summary, problems


def main():
    path = sys.argv[1] if len(sys.argv) > 1 else os.path.join(ROOT, "schema", "data.yaml")
    sv = SchemaView(path)
    modalities = set(sv.get_enum("ModalityEnum").permissible_values)
    set_classes = file_set_classes(path)
    bad = []
    for name in sorted(sv.class_descendants("DataFile", reflexive=False)):
        if sv.get_class(name).abstract:
            continue
        summary, problems = check_class(sv, name, modalities, set_classes)
        bad += [name] if problems else []
        print(f"{'ok  ' if not problems else 'FAIL'} {name}: {summary}")
        for p in problems:
            print(f"       {p}")
    print(f"\n{len(bad)} failure(s)")
    sys.exit(1 if bad else 0)


if __name__ == "__main__":
    main()
