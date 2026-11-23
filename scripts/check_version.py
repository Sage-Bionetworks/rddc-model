"""Check that the schema version is consistent.

1. Every LinkML module in schema/ has the same `version`.
2. The example sidecars and source descriptor declare that version in conformsTo.
3. On a release tag (v<major>.<minor>.<patch>), the tag matches the version.
   The tag is read from the first argument, else from GITHUB_REF_NAME when
   GITHUB_REF_TYPE is "tag".
"""
import glob
import json
import os
import re
import sys

import yaml

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
URI = re.compile(r"^https://w3id\.org/rddc/(sidecar|source-descriptor)/(.+)$")


def main():
    errors = []
    versions = {}
    for path in sorted(glob.glob(os.path.join(ROOT, "schema", "*.yaml"))):
        versions[os.path.relpath(path, ROOT)] = str(yaml.safe_load(open(path)).get("version"))
    distinct = set(versions.values())
    if len(distinct) != 1:
        errors.append("modules disagree on version: " + ", ".join(f"{p}={v}" for p, v in versions.items()))
    version = versions.get("schema/rddc_sidecar.yaml")

    for path in sorted(glob.glob(os.path.join(ROOT, "examples", "*.json"))):
        for uri in json.load(open(path)).get("conformsTo", []):
            m = URI.match(uri)
            if m and m.group(2) != version:
                errors.append(f"{os.path.relpath(path, ROOT)}: conformsTo {uri} does not match schema version {version}")

    tag = sys.argv[1] if len(sys.argv) > 1 else (
        os.environ.get("GITHUB_REF_NAME") if os.environ.get("GITHUB_REF_TYPE") == "tag" else None)
    if tag and tag != f"v{version}":
        errors.append(f"tag {tag} does not match schema version {version} (expected v{version})")

    for e in errors:
        print("FAIL", e)
    print(f"schema version {version}" + (f", tag {tag}" if tag else "") + f": {len(errors)} failure(s)")
    sys.exit(1 if errors else 0)


if __name__ == "__main__":
    main()
