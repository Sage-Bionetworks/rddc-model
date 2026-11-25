"""Merge src/data/*.yaml into one StandardsCatalog document on stdout.

Fields left empty in the data files (e.g. `selectionStatus:` with no value) are
placeholders for "not yet recorded", so they are dropped rather than passed on
as nulls, which the validator would reject.
"""
import sys
from pathlib import Path

import yaml


def drop_empty(item):
    return {k: v for k, v in item.items() if v is not None} if isinstance(item, dict) else item


merged = {}
for f in sorted(Path(sys.argv[1]).glob("*.yaml")):
    for k, v in (yaml.safe_load(f.read_text()) or {}).items():
        merged.setdefault(k, []).extend(drop_empty(item) for item in v)
yaml.safe_dump(merged, sys.stdout, sort_keys=False, allow_unicode=True, width=100)
