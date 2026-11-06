"""Build the sidecar JSON-LD context: Croissant 1.1's context plus RDDC terms.

Usage: python scripts/build_context.py SCHEMA CROISSANT_CONTEXT OUT [EXAMPLE ...]

Every slot in the LinkML schema gets a term unless the Croissant context
already defines it or schema.org's @vocab covers it. A term the Croissant
context defines must map to the same IRI as the slot, so RDDC never redefines
a Croissant term. Examples given on the command line get their @context
replaced with the result, because mlcroissant requires an embedded context.
"""

import json
import sys

from linkml_runtime.utils.schemaview import SchemaView

SCHEMA_ORG = "https://schema.org/"

# Terms whose values are node IDs (CURIEs or IRIs), not literals.
ID_VALUED = {"additionalType"}


def build(schema_path, croissant_path):
    sv = SchemaView(schema_path)
    base = json.load(open(croissant_path))["@context"]
    ctx = dict(base)
    ctx["rddc"] = sv.schema.prefixes["rddc"].prefix_reference
    ctx["prov"] = sv.schema.prefixes["prov"].prefix_reference

    for name, slot in sorted(sv.all_slots().items()):
        if slot.alias and slot.alias.startswith("@"):
            continue  # JSON-LD keyword (@context, @id, @type)
        iri = sv.expand_curie(slot.slot_uri) if slot.slot_uri else None
        iri = iri or ctx["rddc"] + name
        if name in base:
            mapped = base[name]
            mapped = mapped.get("@id", iri) if isinstance(mapped, dict) else mapped
            mapped_iri = sv.expand_curie(mapped) if ":" in mapped else iri
            if mapped_iri != iri:
                raise SystemExit(f"slot {name} maps to {iri} but Croissant maps it to {mapped_iri}")
            continue
        if iri == SCHEMA_ORG + name and name not in ID_VALUED:
            continue  # covered by "@vocab": "https://schema.org/"
        curie = next((f"{p}:{iri[len(ctx[p]):]}" for p in ("rddc", "prov", "cr", "dct", "sc")
                      if iri.startswith(ctx[p])), iri)
        ctx[name] = {"@id": curie, "@type": "@id"} if name in ID_VALUED else curie
    return ctx


def main():
    schema_path, croissant_path, out_path, *examples = sys.argv[1:]
    ctx = build(schema_path, croissant_path)
    with open(out_path, "w") as f:
        json.dump({"@context": ctx}, f, indent=2)
        f.write("\n")
    for path in examples:
        doc = json.load(open(path))
        if "@context" not in doc:
            continue  # not a sidecar (e.g. a source descriptor)
        doc = {"@context": ctx, **{k: v for k, v in doc.items() if k != "@context"}}
        with open(path, "w") as f:
            json.dump(doc, f, indent=2)
            f.write("\n")


if __name__ == "__main__":
    main()
