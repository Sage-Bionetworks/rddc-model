"""Generate docs/data_classes.md, the reference page for the data file classes.

Usage: python scripts/gen_docs.py [--check] [--schema SCHEMA] [--out OUT]

Reads schema/data.yaml (and core.yaml, which it imports) and writes one Markdown page:
the class hierarchy, a summary table, every data file class with its fields and rules,
the supporting classes and types they use, and the enums. With --check, nothing is
written: the script exits 1 if OUT differs from what the schema generates.
"""

import argparse
import os
import re
import sys

from linkml_runtime.utils.schemaview import SchemaView

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
ROOT_CLASS = "DataFile"
FLAGS = ("containsDates", "containsZipCodes", "containsFreeText", "containsBiometricIdentifiers")
FLAG_WORDS = {"always": "always true", "n/a": "not applicable, so false", "false": "false unless set"}
COMPACT_ENUM = 20  # enums with more values are listed inline, without descriptions


def one_line(text):
    return " ".join((text or "").split())


def first_sentence(text):
    text = one_line(text)
    end = text.find(". ")
    return text if end < 0 else text[:end + 1]


def code(text):
    """Inline code for a table cell: GitHub tables need | escaped even inside backticks."""
    return "`" + str(text).replace("|", "\\|") + "`"


def cell(text):
    return one_line(text).replace("|", "\\|")


class Page:
    def __init__(self, sv):
        self.sv = sv
        self.classes = [c for c in self.walk(ROOT_CLASS)]
        self.enums, self.types, self.support = [], [], []
        self.collect()

    # --- what to document ---------------------------------------------------------

    def walk(self, name):
        """ROOT_CLASS and its descendants, depth first, children in schema order."""
        yield name
        for child in self.sv.class_children(name):
            yield from self.walk(child)

    def collect(self):
        """Enums, types and supporting classes reachable from the data file classes."""
        seen, queue = set(self.classes), list(self.classes)
        while queue:
            for slot in self.sv.class_induced_slots(queue.pop()):
                rng = slot.range or self.sv.schema.default_range
                if rng in self.sv.all_enums() and rng not in self.enums:
                    self.enums.append(rng)
                elif rng in self.sv.all_types() and not self.builtin(rng) and rng not in self.types:
                    self.types.append(rng)
                elif rng in self.sv.all_classes() and rng not in seen:
                    seen.add(rng)
                    self.support.append(rng)
                    queue.append(rng)
        # Enums named only by rules (per-version value lists) belong on the page too.
        own = [e for e in self.sv.schema.enums or {}] if self.sv.schema.enums else []
        for name in own:
            if name not in self.enums:
                self.enums.append(name)
        order = list(self.sv.all_enums())
        self.enums.sort(key=order.index)
        self.types.sort(key=list(self.sv.all_types()).index)

    def builtin(self, type_name):
        return (self.sv.get_type(type_name).from_schema or "").startswith("https://w3id.org/linkml/")

    # --- pieces -------------------------------------------------------------------

    def link(self, name):
        return f"[`{name}`](#{name.lower()})"

    def range_text(self, slot):
        rng = slot.range or self.sv.schema.default_range
        if rng in self.enums or rng in self.types or rng in self.support or rng in self.classes:
            text = self.link(rng)
        else:
            text = f"`{rng}`"
        return text + (" (list)" if slot.multivalued else "")

    def constraints(self, slot):
        out = []
        if slot.equals_string:
            out.append(f"Fixed: `{slot.equals_string}`.")
        values = [a.equals_string for a in slot.any_of or [] if a.equals_string]
        if values:
            out.append("One of: " + ", ".join(f"`{v}`" for v in values) + ".")
        excluded = [n.equals_string for n in slot.none_of or [] if n.equals_string]
        if excluded:
            out.append("Not: " + ", ".join(f"`{v}`" for v in excluded) + ".")
        if slot.pattern and not slot.equals_string:
            out.append(f"Pattern: {code(slot.pattern)}.")
        if slot.minimum_value is not None:
            out.append(f"Minimum: {slot.minimum_value}.")
        if slot.maximum_value is not None:
            out.append(f"Maximum: {slot.maximum_value}.")
        return " ".join(out)

    def enum_for_values(self, values):
        """The enum whose values are exactly this list, preferring a per-version enum over a union."""
        matches = [e for e in self.enums if set(self.sv.get_enum(e).permissible_values) == set(values)]
        used_as_range = {s.range for c in self.classes for s in self.sv.class_induced_slots(c)}
        matches.sort(key=lambda e: e in used_as_range)
        return matches[0] if matches else None

    def rule_text(self, rule):
        pre = rule.preconditions.slot_conditions if rule.preconditions else {}
        post = rule.postconditions.slot_conditions if rule.postconditions else {}
        if len(pre) == 1 and len(post) == 1:
            (p_name, p), (q_name, q) = next(iter(pre.items())), next(iter(post.items()))
            if p.equals_string and q.equals_string_in:
                enum = self.enum_for_values(q.equals_string_in)
                allowed = (f"a value of {self.link(enum)}" if enum
                           else f"one of {len(q.equals_string_in)} listed values")
                return f"If `{p_name}` is `{p.equals_string}`, `{q_name}` must be {allowed}."
        return cell(rule.description) or "(rule without description)"

    def signature(self, slot):
        return (slot.range, slot.required, slot.multivalued, slot.equals_string, slot.pattern,
                tuple(a.equals_string for a in slot.any_of or []), tuple(n.equals_string for n in slot.none_of or []),
                slot.minimum_value, slot.maximum_value, one_line(slot.description))

    def own_slots(self, name):
        """Fields the class adds or changes relative to its documented parent; all fields for the root."""
        slots = self.sv.class_induced_slots(name)
        parent = self.sv.get_class(name).is_a
        if name == ROOT_CLASS or parent not in self.classes:
            return slots, None
        inherited = {s.name: self.signature(s) for s in self.sv.class_induced_slots(parent)}
        return [s for s in slots if inherited.get(s.name) != self.signature(s)], parent

    def slot_rows(self, name):
        own, parent = self.own_slots(name)
        slots = sorted(own, key=lambda s: (not s.required, s.alias or s.name))
        if not slots:
            return [f"No fields beyond those of {self.link(parent)}."]
        rows = ["| Field | Type | Required | Meaning and constraints |", "| --- | --- | --- | --- |"]
        for s in slots:
            meaning = " ".join(p for p in (cell(s.description), self.constraints(s), self.mappings(s)) if p)
            rows.append(f"| `{s.alias or s.name}` | {self.range_text(s)} | {'yes' if s.required else ''} | "
                        f"{meaning} |".replace("  |", " |"))
        return rows

    # --- sections -----------------------------------------------------------------

    def hierarchy(self):
        bases = list(reversed(self.sv.class_ancestors(ROOT_CLASS)[1:]))
        lines = ["```"]
        lines += [("  " * i) + b for i, b in enumerate(bases)]
        depth0 = len(bases)

        def tree(name, depth):
            cls = self.sv.get_class(name)
            notes = []
            if cls.abstract:
                notes.append("abstract")
            for key in ("structure", "modality"):
                if cls.annotations.get(key):
                    notes.append(cls.annotations[key].value)
            for key, note in (("biometric", "biometric"), ("identifying", "identifying"),
                              ("embedsFiles", "embeds files")):
                if cls.annotations.get(key):
                    notes.append(note)
            lines.append(("  " * depth) + name + (f"  ({', '.join(notes)})" if notes else ""))
            for child in self.sv.class_children(name):
                tree(child, depth + 1)

        tree(ROOT_CLASS, depth0)
        lines.append("```")
        return lines

    def summary(self):
        rows = ["| Class | Modality | Structure | Media types | Class-specific required fields |",
                "| --- | --- | --- | --- | --- |"]
        base = {s.name for s in self.sv.class_induced_slots(ROOT_CLASS) if s.required}
        for name in self.classes:
            cls = self.sv.get_class(name)
            if cls.abstract:
                continue
            slots = {s.name: s for s in self.sv.class_induced_slots(name)}
            fmt = slots["encodingFormat"]
            media = ([fmt.equals_string] if fmt.equals_string
                     else [a.equals_string for a in fmt.any_of or [] if a.equals_string])
            top = re.match(r"\^([a-z]+)/", fmt.pattern or "")
            if not media and top:
                media = [f"{top.group(1)}/*"]
            extra = [s.alias or s.name for s in slots.values() if s.required and s.name not in base]
            structure, modality = (cls.annotations.get(k) for k in ("structure", "modality"))
            rows.append(f"| {self.link(name)} | {f'`{modality.value}`' if modality else ''} | "
                        f"{structure.value if structure else ''} | "
                        f"{', '.join(f'`{m}`' for m in media) or 'any'} | {', '.join(f'`{e}`' for e in extra)} |")
        return rows

    def class_section(self, name, level="###"):
        cls = self.sv.get_class(name)
        out = [f"{level} {name}", "", cell(cls.description), ""]
        facts = []
        if cls.abstract:
            facts.append("Abstract: not used directly.")
        else:
            if name in self.classes:
                facts.append(f'Use as `"@type": "cr:FileObject", "additionalType": "rddc:{name}"`.')
        parents = self.sv.class_ancestors(name)[1:]
        if parents:
            facts.append("Inherits from " + " → ".join(self.link(p) if p in self.classes else f"`{p}`" for p in parents) + ".")
        children = self.sv.class_children(name)
        if children:
            facts.append("Subclasses: " + ", ".join(self.link(c) for c in children) + ".")
        structure = cls.annotations.get("structure")
        if structure:
            facts.append(f"Structure: {structure.value}.")
        modality = cls.annotations.get("modality")
        if modality:
            facts.append(f"Modality: `{modality.value}`.")
        set_class = cls.annotations.get("fileSetClass")
        if set_class:
            facts.append(f"Belongs to a `{set_class.value}` file set, whose `conformsTo` gives its standard and version.")
        fixed = [f"`{f}` {FLAG_WORDS[cls.annotations[f].value]}" for f in FLAGS if cls.annotations.get(f)]
        if fixed:
            facts.append("Sensitivity flags: " + "; ".join(fixed) + ".")
        collection = cls.annotations.get("rai:dataCollectionType")
        if collection:
            facts.append(f"Data collection (`rai:dataCollectionType`): {collection.value}.")
        for kind, label in (("exact_mappings", "Same as"), ("close_mappings", "Close to"),
                            ("broad_mappings", "A kind of"), ("narrow_mappings", "Broader than")):
            terms = getattr(cls, kind) or []
            if terms:
                facts.append(f"{label} " + ", ".join(self.term(t) for t in terms) + ".")
        if cls.annotations.get("biometric"):
            facts.append("Biometric: always counts as containing biometric identifiers, and so as identifying.")
        if cls.annotations.get("identifying"):
            facts.append("Identifying: can identify a person on its own, so it never counts as de-identified.")
        if cls.annotations.get("embedsFiles"):
            facts.append("Embeds files: can carry documents or images inside it, whose content its class "
                         "and sensitivity flags do not describe.")
        out += [" ".join(facts), ""] if facts else []
        own, parent = self.own_slots(name)
        if parent and own:
            out += [f"Fields it adds or changes; it also has all fields of {self.link(parent)}:", ""]
        out += self.slot_rows(name) + [""]
        rules = [r for c in [name] + parents for r in self.sv.get_class(c).rules or []]
        if rules:
            out += ["Rules:", ""] + [f"- {self.rule_text(r)}" for r in rules] + [""]
        return out

    def enum_section(self, name):
        enum = self.sv.get_enum(name)
        values = enum.permissible_values
        out = [f"### {name}", "", cell(enum.description), ""]
        annotated = any(pv.annotations for pv in values.values())
        if annotated:
            keys = list(dict.fromkeys(k for pv in values.values() for k in pv.annotations))
            out += ["| Value | Meaning | " + " | ".join(keys) + " |", "| --- | --- |" + " --- |" * len(keys)]
            out += [f"| `{v}` | {cell(first_sentence(pv.description))} | "
                    + " | ".join(cell(pv.annotations[k].value) if k in pv.annotations else "" for k in keys)
                    + " |" for v, pv in values.items()]
        elif len(values) > COMPACT_ENUM:
            out.append(f"{len(values)} values: " + ", ".join(f"`{v}`" for v in values) + ".")
        elif any(pv.meaning for pv in values.values()):
            out += ["| Value | Term | Meaning |", "| --- | --- | --- |"]
            out += [f"| `{v}` | {self.value_terms(pv)} | {cell(pv.description)} |" for v, pv in values.items()]
        else:
            out += ["| Value | Meaning |", "| --- | --- |"]
            out += [f"| `{v}` | {cell(pv.description)} |" for v, pv in values.items()]
        return out + [""]

    def value_terms(self, pv):
        """A value's meaning, or failing that its mappings, e.g. "close: NCIT:C190554"."""
        if pv.meaning:
            return self.term(pv.meaning)
        parts = [f"{label}: " + ", ".join(self.term(t) for t in getattr(pv, kind) or [])
                 for kind, label in (("close_mappings", "close"), ("broad_mappings", "broader"))
                 if getattr(pv, kind)]
        return "; ".join(parts)

    MAPPING_LABELS = (("exact_mappings", "Same as"), ("close_mappings", "Close to"),
                      ("broad_mappings", "Narrower than"), ("narrow_mappings", "Broader than"),
                      ("related_mappings", "Related to"))

    def mappings(self, element):
        """A slot's mappings to external terms, e.g. "Close to pd:Biometric."."""
        return " ".join(f"{label} " + ", ".join(self.term(t) for t in getattr(element, kind)) + "."
                        for kind, label in self.MAPPING_LABELS if getattr(element, kind, None))

    def term(self, curie):
        """An ontology term as a link to its IRI, or empty when the value has none."""
        return f"[`{curie}`]({self.sv.expand_curie(curie)})" if curie else ""

    def type_rows(self):
        rows = ["| Type | Base | Meaning | Pattern |", "| --- | --- | --- | --- |"]
        for name in self.types:
            t = self.sv.get_type(name)
            rows.append(f"| <a id=\"{name.lower()}\"></a>`{name}` | `{t.typeof}` | {cell(t.description)} | "
                        f"{code(t.pattern) if t.pattern else ''} |")
        return rows

    @staticmethod
    def description_lines(text):
        """Folded YAML keeps more-indented lines verbatim: '  term: text' starts a list item."""
        out = []
        for line in (text or "").split("\n"):
            indent = len(line) - len(line.lstrip())
            if indent == 2 and ": " in line:
                term, rest = line.strip().split(": ", 1)  # a term may be a CURIE (rai:dataCollectionType)
                rest = " " + rest
                out.append(f"- **{term}**:{rest}")
            elif indent > 2 and out:
                out[-1] += " " + line.strip()
            elif line.strip():
                out += ["", line.strip()]
        return out

    def render(self):
        schema = self.sv.schema
        out = [
            "<!-- Generated by scripts/gen_docs.py from schema/data.yaml. Do not edit; run `make docs`. -->",
            "",
            "# Data file classes",
            "",
            f"Schema module `{schema.name}` ({schema.id}), version {schema.version}.",
            "",
            *self.description_lines(schema.description),
            "",
            "## Hierarchy",
            "",
            *self.hierarchy(),
            "",
            "## Summary",
            "",
            "Every concrete class also requires the fields shared by all data files: "
            + ", ".join(f"`{s.alias or s.name}`" for s in sorted(self.sv.class_induced_slots(ROOT_CLASS),
                                                                   key=lambda s: s.alias or s.name) if s.required)
            + ".",
            "",
            *self.summary(),
            "",
            "## Classes",
            "",
        ]
        for name in self.classes:
            out += self.class_section(name)
        out += ["## Supporting classes", "", "Classes used as field types above. They are defined in core.yaml or data.yaml.", ""]
        for name in self.support:
            out += self.class_section(name)
        out += ["## Enumerations", ""]
        for name in self.enums:
            out += self.enum_section(name)
        out += ["## Types", "", *self.type_rows(), ""]
        return "\n".join(out).replace("\n\n\n", "\n\n")


def main():
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--schema", default=os.path.join(ROOT, "schema", "data.yaml"))
    parser.add_argument("--out", default=os.path.join(ROOT, "docs", "data_classes.md"))
    parser.add_argument("--check", action="store_true", help="report whether OUT is up to date; write nothing")
    args = parser.parse_args()

    text = Page(SchemaView(args.schema)).render()
    current = open(args.out, encoding="utf-8").read() if os.path.exists(args.out) else None
    if args.check:
        print(f"{os.path.relpath(args.out, ROOT)}: {'up to date' if current == text else 'OUT OF DATE; run make docs'}")
        sys.exit(0 if current == text else 1)
    os.makedirs(os.path.dirname(args.out), exist_ok=True)
    if current != text:
        with open(args.out, "w", encoding="utf-8") as f:
            f.write(text)
    print(f"wrote {os.path.relpath(args.out, ROOT)}")


if __name__ == "__main__":
    main()
