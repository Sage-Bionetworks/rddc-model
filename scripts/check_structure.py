"""Check the class annotations on the data file classes.

Usage: python scripts/check_structure.py [SCHEMA]

SCHEMA defaults to schema/data.yaml. LinkML does not validate annotation values,
so this script does. Exits non-zero if any concrete DataFile subclass has no
"structure" annotation or an unknown value, or if any class has a "biometric"
annotation other than "true".
"""

import os
import sys

from linkml_runtime.utils.schemaview import SchemaView

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
STRUCTURES = {"structured", "unstructured", "mixed"}
BIOMETRIC = {"true"}


def main():
    path = sys.argv[1] if len(sys.argv) > 1 else os.path.join(ROOT, "schema", "data.yaml")
    sv = SchemaView(path)
    bad = []
    for name in sorted(sv.class_descendants("DataFile", reflexive=False)):
        cls = sv.get_class(name)
        if cls.abstract:
            continue
        ann = cls.annotations.get("structure")
        value = ann.value if ann is not None else None
        biometric = cls.annotations.get("biometric")
        ok = value in STRUCTURES and (biometric is None or biometric.value in BIOMETRIC)
        bad += [] if ok else [name]
        extra = f", biometric: {biometric.value}" if biometric is not None else ""
        print(f"{'ok  ' if ok else 'FAIL'} {name}: {value}{extra}")
    print(f"\n{len(bad)} failure(s)")
    sys.exit(1 if bad else 0)


if __name__ == "__main__":
    main()
