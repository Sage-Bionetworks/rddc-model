"""Merge src/data/*.yaml into one StandardsCatalog document on stdout."""
import sys
from pathlib import Path

import yaml

merged = {}
for f in sorted(Path(sys.argv[1]).glob("*.yaml")):
    for k, v in (yaml.safe_load(f.read_text()) or {}).items():
        merged.setdefault(k, []).extend(v)
yaml.safe_dump(merged, sys.stdout, sort_keys=False, allow_unicode=True, width=100)
