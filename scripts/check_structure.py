"""Check the class annotations on the data file classes.

Usage: python scripts/check_structure.py [SCHEMA]

SCHEMA defaults to schema/data.yaml. LinkML does not validate annotation values,
so this script does. Exits non-zero if any concrete DataFile subclass:

- has no "structure" annotation, or an unknown value;
- has no "modality" annotation, or a value that is not in ModalityEnum;
- has a "biometric" annotation other than "true", or is a subclass of a
  biometric class and does not repeat the annotation;
- has an "rai:dataCollectionType" annotation that is not one of the Croissant
  Responsible AI recommended values (the annotation is optional).
"""

import os
import sys

from linkml_runtime.utils.schemaview import SchemaView

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
STRUCTURES = {"structured", "unstructured", "mixed"}
BIOMETRIC = {"true"}
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


def main():
    path = sys.argv[1] if len(sys.argv) > 1 else os.path.join(ROOT, "schema", "data.yaml")
    sv = SchemaView(path)
    modalities = set(sv.get_enum("ModalityEnum").permissible_values)
    bad = []
    for name in sorted(sv.class_descendants("DataFile", reflexive=False)):
        cls = sv.get_class(name)
        if cls.abstract:
            continue
        structure, modality, biometric, collection = (
            value(cls, k) for k in ("structure", "modality", "biometric", "rai:dataCollectionType"))
        # A subclass of a biometric class identifies a person too, so it must say so.
        inherited = any(
            value(sv.get_class(a), "biometric") is not None
            for a in sv.class_ancestors(name, reflexive=False)
        )
        ok = (
            structure in STRUCTURES
            and modality in modalities
            and (biometric is None or biometric in BIOMETRIC)
            and (biometric is not None or not inherited)
            and (collection is None or collection in COLLECTION_TYPES)
        )
        bad += [] if ok else [name]
        extra = f", biometric: {biometric}" if biometric is not None else ""
        extra += f", collected by: {collection}" if collection is not None else ""
        print(f"{'ok  ' if ok else 'FAIL'} {name}: {structure}, {modality}{extra}")
    print(f"\n{len(bad)} failure(s)")
    sys.exit(1 if bad else 0)


if __name__ == "__main__":
    main()
