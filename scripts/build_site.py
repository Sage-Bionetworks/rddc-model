"""Build the static documentation site.

Usage: python scripts/build_site.py [OUT]   (default: site/dist)

Pages are HTML fragments in site/pages; the reference and vocabulary pages are
generated from schema/rddc_sidecar.yaml, so they always describe the schema in
this checkout. Fragments may use two directives:

  <rddc-json src="examples/x.json" pointer="/distribution/0" keys="a,b"
             title="..."></rddc-json>
      A JSON file (or the node at a JSON pointer, or a subset of its keys),
      pretty-printed and highlighted. @context is shown elided.

  <rddc-code title="..." [lang="json|text|shell"]>RAW</rddc-code>
      Literal code. JSON is highlighted the same way.

JSON keys are tagged with the vocabulary they come from (schema.org,
Croissant, RDDC, PROV), read from the generated JSON-LD context.

Every site/recipes/*.json is validated against the sidecar JSON Schema (with
the generated @context added), and every site/recipes/mistakes/*.json must
fail it; the build stops otherwise.
"""

import glob
import html
import json
import os
import re
import shutil
import sys

import jsonschema
from linkml_runtime.utils.schemaview import SchemaView

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SITE = os.path.join(ROOT, "site")
SCHEMA = os.path.join(ROOT, "schema", "rddc_sidecar.yaml")
GEN = os.path.join(ROOT, "schema", "generated")
CONTEXT = json.load(open(os.path.join(GEN, "rddc_sidecar.context.jsonld")))["@context"]

sv = SchemaView(SCHEMA)
VERSION = sv.schema.version

# Navigation: (group, [(file, title)]). The order is the reading order.
NAV = [
    ("Start here", [
        ("index.html", "Overview"),
        ("foundations.html", "Foundations"),
        ("croissant.html", "RDDC and Croissant"),
    ]),
    ("Learn", [
        ("concepts.html", "Core concepts"),
        ("tutorial.html", "Sidecar tutorial"),
        ("lifecycle.html", "Lifecycle and validation"),
    ]),
    ("Examples", [
        ("examples.html", "Example sidecars"),
        ("recipes.html", "Recipes by data type"),
        ("mistakes.html", "Common mistakes"),
    ]),
    ("Reference", [
        ("reference.html", "Schema reference"),
        ("vocabularies.html", "Controlled vocabularies"),
        ("source-descriptor.html", "Source descriptor"),
        ("glossary.html", "Glossary and FAQ"),
        ("downloads.html", "Downloads"),
    ]),
]
PAGES = [p for _, items in NAV for p in items]

ORIGIN_LABEL = {
    "sc": "schema.org",
    "cr": "Croissant",
    "rddc": "RDDC",
    "prov": "W3C PROV",
    "kw": "JSON-LD keyword",
}


# ---------------------------------------------------------------------------
# Term origins
# ---------------------------------------------------------------------------
def expand(curie):
    prefix, _, local = curie.partition(":")
    base = CONTEXT.get(prefix)
    return base + local if isinstance(base, str) and local else curie


def term_origin(key):
    """(origin class, IRI) for a JSON key."""
    if key.startswith("@"):
        return "kw", "JSON-LD keyword " + key
    mapped = CONTEXT.get(key)
    if isinstance(mapped, dict):
        mapped = mapped.get("@id")
    iri = expand(mapped) if mapped else "https://schema.org/" + key
    if iri.startswith(CONTEXT["rddc"]):
        return "rddc", iri
    if iri.startswith(CONTEXT["cr"]) or iri.startswith(CONTEXT["dct"]):
        return "cr", iri
    if iri.startswith(CONTEXT["prov"]):
        return "prov", iri
    return "sc", iri


def slot_origin(slot):
    key = slot.alias or slot.name
    return term_origin(key)


# ---------------------------------------------------------------------------
# JSON highlighting
# ---------------------------------------------------------------------------
TOKEN = re.compile(
    r'("(?:[^"\\]|\\.)*")(\s*:)?'
    r"|(-?\d+(?:\.\d+)?(?:[eE][+-]?\d+)?)"
    r"|\b(true|false|null)\b"
    r"|([{}\[\],])"
)
ELIDED = "__ELIDED_CONTEXT__"
MORE = "__OMITTED__"


def compact_json(value, indent=0, width=64, col=None):
    """Pretty-print JSON, keeping objects and arrays on one line when they fit.

    indent is the nesting indentation; col is the column where the value starts
    (after its key), used to decide whether it fits on one line.
    """
    col = indent if col is None else col
    inline = json.dumps(value, ensure_ascii=False, separators=(", ", ": "))
    if col + len(inline) <= width or not isinstance(value, (dict, list)) or not value:
        return inline
    pad, inner = " " * indent, " " * (indent + 2)
    if isinstance(value, dict):
        items = []
        for k, v in value.items():
            key = json.dumps(k) + ": "
            items.append(inner + key + compact_json(v, indent + 2, width, indent + 2 + len(key)))
        return "{\n" + ",\n".join(items) + "\n" + pad + "}"
    items = [inner + compact_json(v, indent + 2, width) for v in value]
    return "[\n" + ",\n".join(items) + "\n" + pad + "]"


def slide_example():
    """Excerpts of examples/deposit_fhir_omop.json for the example slide."""
    doc = json.load(open(os.path.join(ROOT, "examples", "deposit_fhir_omop.json")))
    header_keys = ["@context", "@id", "@type", "conformsTo", "name", "wasAttributedTo",
                   "contributorId", "sourceId", "batchId", "interaction", "sensitivity", "subjects"]
    header = {k: (ELIDED if k == "@context" else doc[k]) for k in header_keys}
    header["subjects"] = header["subjects"][:2] + [MORE]
    header["distribution"] = [MORE]
    by_id = {node["@id"]: node for node in doc["distribution"]}
    file_node = {k: v for k, v in by_id["urn:uuid:0000000b-0000-4000-8000-00000000000b"].items()
                 if k != "md5"}
    file_set = dict(by_id["fhir_export"])
    return {
        "header": compact_json(header),
        "files": compact_json([file_set, file_node, MORE], width=84),
    }


def class_yaml(name):
    """A class's block from the schema source, verbatim apart from descriptions."""
    lines = open(SCHEMA).read().splitlines()
    start = lines.index(f"  {name}:")
    block = [lines[start]]
    for line in lines[start + 1:]:
        if line.strip() and not line.startswith("    "):
            break
        block.append(line)
    while block and not block[-1].strip():
        block.pop()
    out, skip_deeper_than = [], None
    for line in block:
        depth = len(line) - len(line.lstrip())
        if skip_deeper_than is not None:
            if depth > skip_deeper_than or not line.strip():
                continue
            skip_deeper_than = None
        if line.lstrip().startswith("description:"):
            skip_deeper_than = depth
            continue
        out.append(line[2:])
    # Drop slot_usage entries left empty once their description is gone.
    kept = []
    for i, line in enumerate(out):
        nxt = out[i + 1] if i + 1 < len(out) else ""
        depth = len(line) - len(line.lstrip())
        if line.rstrip().endswith(":") and depth >= 4 and len(nxt) - len(nxt.lstrip()) <= depth:
            continue
        kept.append(line)
    return "\n".join(kept)


def slide_linkml():
    """Schema excerpts for the LinkML slide: the classes behind the example entries."""
    return {
        "file": class_yaml("FileObject"),
        "fhir": class_yaml("DataFile") + "\n\n" + class_yaml("FhirNdjsonFile"),
        "set": class_yaml("FhirBulkExport"),
    }


YAML_LINE = re.compile(r"^(\s*)(- )?([A-Za-z_@][\w@]*)(:?)(.*)$")


def highlight_yaml(text):
    """Highlight a LinkML excerpt; slot names get the colour of their vocabulary."""
    out = []
    section = None
    for line in text.split("\n"):
        m = YAML_LINE.match(line)
        if not m:
            out.append(html.escape(line))
            continue
        indent, dash, word, colon, rest = m.groups()
        depth = len(indent)
        if depth == 0:
            out.append(f'{indent}<span class="cls">{html.escape(word)}</span>{colon}{html.escape(rest)}')
            continue
        if depth == 2 and not dash:
            section = word
        slot = (section == "slots" and dash) or (section == "slot_usage" and depth == 4)
        if slot and sv.get_slot(word) is not None:
            origin, iri = slot_origin(sv.get_slot(word))
            key = f'<span class="k o-{origin}" title="{html.escape(ORIGIN_LABEL[origin])}: {html.escape(iri)}">{html.escape(word)}</span>'
        else:
            key = f'<span class="yk">{html.escape(word)}</span>'
        value = rest
        if value.strip():
            v = value.strip()
            cls = "cls" if word == "is_a" else "s"
            value = value[: len(value) - len(value.lstrip())] + f'<span class="{cls}">{html.escape(v)}</span>'
        out.append(f'{indent}{html.escape(dash or "")}{key}{colon}{value}')
    return "\n".join(out)


def highlight_json(text):
    out, pos = [], 0
    for m in TOKEN.finditer(text):
        out.append(html.escape(text[pos:m.start()]))
        pos = m.end()
        string, colon, number, literal, punct = m.groups()
        if string and colon:
            key = json.loads(string)
            origin, iri = term_origin(key)
            out.append(
                f'<span class="k o-{origin}" title="{html.escape(ORIGIN_LABEL[origin])}: '
                f'{html.escape(iri)}">{html.escape(string)}</span>{html.escape(colon)}'
            )
        elif string:
            if string == f'"{ELIDED}"':
                out.append('<span class="elided" title="The embedded JSON-LD context: Croissant 1.1 '
                           'plus the RDDC terms. See Downloads.">{ … }</span>')
            elif string == f'"{MORE}"':
                out.append('<span class="elided" title="Omitted from this excerpt">…</span>')
            else:
                out.append(f'<span class="s">{html.escape(string)}</span>')
        elif number:
            out.append(f'<span class="n">{number}</span>')
        elif literal:
            out.append(f'<span class="l">{literal}</span>')
        else:
            out.append(f'<span class="p">{punct}</span>')
    out.append(html.escape(text[pos:]))
    return "".join(out)


def dumps(node):
    return json.dumps(node, indent=2, ensure_ascii=False)


def esc(text):
    return html.escape(text or "")


def code_block(body_html, title=None, lang="json", download=None):
    head = ""
    if title or download:
        link = f'<a class="dl" href="{download}" download>Download</a>' if download else ""
        head = f'<figcaption><span>{title or ""}</span>{link}</figcaption>'
    return (
        f'<figure class="code" data-lang="{lang}">{head}'
        f'<pre><code>{body_html}</code></pre>'
        f'<button class="copy" type="button" aria-label="Copy code">Copy</button></figure>'
    )


def resolve_pointer(doc, pointer):
    for part in [p for p in pointer.split("/") if p]:
        part = part.replace("~1", "/").replace("~0", "~")
        doc = doc[int(part)] if isinstance(doc, list) else doc[part]
    return doc


def render_json_directive(m):
    attrs = dict(re.findall(r'(\w+)="([^"]*)"', m.group(1)))
    src = attrs["src"]
    doc = json.load(open(os.path.join(ROOT, src)))
    node = resolve_pointer(doc, attrs.get("pointer", ""))
    if "keys" in attrs and isinstance(node, dict):
        keys = [k.strip() for k in attrs["keys"].split(",")]
        node = {k: node[k] for k in keys if k in node}
    if src.startswith("site/recipes/") and not attrs.get("pointer") and "@id" in doc and "@context" not in doc:
        if "keys" not in attrs or "@context" in attrs["keys"]:
            node = {"@context": ELIDED, **node}
    if isinstance(node, dict) and "@context" in node:
        node = {**node, "@context": ELIDED}
    download = None
    if src.startswith("examples/") or (src.startswith("site/recipes/") and "/mistakes/" not in src):
        download = "downloads/" + ("examples/" if src.startswith("examples/") else "recipes/") + os.path.basename(src)
    title = attrs.get("title") or os.path.basename(src) + (attrs.get("pointer") or "")
    return code_block(highlight_json(dumps(node)), html.escape(title), download=download)


def render_code_directive(m):
    attrs = dict(re.findall(r'(\w+)="([^"]*)"', m.group(1)))
    raw = m.group(2).strip("\n")
    lang = attrs.get("lang", "json")
    body = highlight_json(raw) if lang == "json" else html.escape(raw)
    return code_block(body, attrs.get("title"), lang=lang)


def expand_directives(text):
    text = re.sub(r"<rddc-json([^>]*)></rddc-json>", render_json_directive, text)
    text = re.sub(r"<rddc-code([^>]*)>(.*?)</rddc-code>", render_code_directive, text, flags=re.S)
    return text


# ---------------------------------------------------------------------------
# Schema reference
# ---------------------------------------------------------------------------
CLASS_GROUPS = [
    ("The sidecar document", "The dataset and its main sections.",
     ["Sidecar", "Agent", "SensitivityDeclaration", "SubjectEntry"]),
    ("Distribution: the common base", "Shared by every file and file set.",
     ["DistributionItem", "FileObject", "DataFile", "FileSensitivity"]),
    ("File classes", "Name one of these in a file's additionalType. @type stays cr:FileObject.",
     ["FhirNdjsonFile", "FhirBundleFile", "FhirResourceFile", "OmopTableFile", "CcdaDocumentFile",
      "TabularFile", "ClinicalDocumentFile", "DocumentationFile", "GenomicsFile", "SequenceReadsFile",
      "AlignmentFile", "VariantFile", "IndexFile", "ImagingFile", "MediaFile", "GenericFile"]),
    ("File set classes", "Name one of these in a file set's additionalType. @type stays cr:FileSet.",
     ["FileSet", "FhirBulkExport", "FhirBundleCollection", "OmopCdmInstance", "CdmSource",
      "CcdaDocumentSet", "TabularDataset", "DocumentSet", "FileCollection"]),
    ("Record sets", "Croissant's table structure, used for data dictionaries and joins.",
     ["RecordSet", "RecordSetField", "FieldSource", "Extract", "FieldReference"]),
    ("Provenance and annotations", "Supporting objects used in several places.",
     ["NodeRef", "ValueOrigin", "ExternalIdentifier", "Extension", "ProcessingHint"]),
    ("Source descriptor", "A separate plain-JSON document; not part of the sidecar.",
     ["SourceDescriptor"]),
]
covered = {c for _, _, cs in CLASS_GROUPS for c in cs}
missing = set(sv.all_classes()) - covered - {"AnyValue"}
if missing:
    raise SystemExit(f"classes missing from CLASS_GROUPS: {sorted(missing)}")


def range_link(rng):
    if rng in sv.all_classes() and rng != "AnyValue":
        return f'<a href="reference.html#{rng}"><code>{rng}</code></a>'
    if rng in sv.all_enums():
        return f'<a href="vocabularies.html#{rng}"><code>{rng}</code></a>'
    if rng in sv.schema.types:
        return f'<a href="vocabularies.html#type-{rng}"><code>{rng}</code></a>'
    if rng == "AnyValue":
        return "<code>object</code>"
    return f"<code>{rng}</code>"


def slot_constraints(slot):
    notes = []
    if slot.equals_string:
        notes.append(f"Must be <code>{html.escape(slot.equals_string)}</code>.")
    if slot.any_of:
        vals = [a.equals_string for a in slot.any_of if a.equals_string]
        if vals:
            notes.append("One of " + ", ".join(f"<code>{html.escape(v)}</code>" for v in vals) + ".")
    if slot.pattern:
        notes.append(f'Pattern <code class="pattern">{html.escape(slot.pattern)}</code>.')
    if slot.minimum_value is not None or slot.maximum_value is not None:
        lo = slot.minimum_value if slot.minimum_value is not None else "…"
        hi = slot.maximum_value if slot.maximum_value is not None else "…"
        notes.append(f"Range {lo} to {hi}.")
    return " ".join(notes)


def condition_text(expr):
    """Render a LinkML rule condition as a short phrase."""
    parts = []
    for name, cond in (expr.slot_conditions or {}).items():
        if cond.equals_string:
            parts.append(f"<code>{name}</code> is <code>{cond.equals_string}</code>")
        elif cond.any_of:
            vals = " or ".join(f"<code>{a.equals_string}</code>" for a in cond.any_of)
            parts.append(f"<code>{name}</code> is {vals}")
        elif cond.required:
            parts.append(f"<code>{name}</code> is present")
    if expr.any_of:
        parts.append("either " + " or ".join(condition_text(e) for e in expr.any_of))
    if expr.exactly_one_of:
        parts.append("exactly one of " + " or ".join(condition_text(e) for e in expr.exactly_one_of))
    return " and ".join(parts)


def rule_text(rule):
    pre = condition_text(rule.preconditions) if rule.preconditions else ""
    post = condition_text(rule.postconditions) if rule.postconditions else ""
    post = post.replace(" is present", " is required")
    sentence = f"When {pre}, {post}." if pre else f"{post}."
    if rule.description:
        return f"<strong>{html.escape(rule.description)}</strong> <span class='muted'>{sentence}</span>"
    return sentence


def class_section(name):
    cls = sv.get_class(name)
    ancestors = sv.class_ancestors(name)[1:]
    children = sorted(sv.class_children(name))
    badges = []
    if cls.abstract:
        badges.append('<span class="badge">abstract</span>')
    meta = []
    if cls.class_uri:
        prefix = cls.class_uri.split(":")[0]
        o = {"sc": "sc", "cr": "cr", "prov": "prov", "linkml": "kw"}.get(prefix, "rddc")
        meta.append(f'<span class="chip o-{o}">{html.escape(cls.class_uri)}</span>')
    if cls.is_a:
        chain = " → ".join(f'<a href="#{a}">{a}</a>' for a in reversed(ancestors))
        meta.append(f"<span>Inherits from {chain}</span>")
    if children:
        meta.append("<span>Subclasses: " + ", ".join(f'<a href="#{c}">{c}</a>' for c in children) + "</span>")
    if name in DISPATCHED:
        typ = "cr:FileSet" if "FileSet" in sv.class_ancestors(name) else "cr:FileObject"
        meta.append(f'<span>Use as <code>"@type": "{typ}", "additionalType": "rddc:{name}"</code></span>')

    rows = []
    for slot in sorted(sv.class_induced_slots(name), key=lambda s: (not s.required, s.alias or s.name)):
        key = slot.alias or slot.name
        origin, iri = slot_origin(slot)
        card = "list" if slot.multivalued else ""
        req = '<span class="req">required</span>' if slot.required else '<span class="opt">optional</span>'
        desc = esc(slot.description)
        cons = slot_constraints(slot)
        rows.append(
            f"<tr><td><code class='k o-{origin}' title='{html.escape(ORIGIN_LABEL[origin])}: {html.escape(iri)}'>{html.escape(key)}</code></td>"
            f"<td>{range_link(slot.range or 'string')}{' <span class=muted>list</span>' if card else ''}</td>"
            f"<td>{req}</td><td>{desc} {cons}</td></tr>"
        )
    rules = [rule_text(r) for c in [name] + ancestors for r in (sv.get_class(c).rules or [])]
    rules_html = ""
    if rules:
        rules_html = "<div class='rules'><h4>Conditional rules</h4><ul>" + "".join(f"<li>{r}</li>" for r in rules) + "</ul></div>"
    table = ""
    if rows:
        table = (
            "<div class='table-wrap'><table class='props'><thead><tr><th>Property</th><th>Type</th>"
            "<th>Required?</th><th>Meaning and constraints</th></tr></thead><tbody>"
            + "".join(rows) + "</tbody></table></div>"
        )
    return (
        f"<section class='class' id='{name}'><h3>{name} {''.join(badges)}</h3>"
        f"<p>{esc(cls.description)}</p><p class='meta'>{''.join(meta)}</p>{table}{rules_html}</section>"
    )


def concrete_descendants(root):
    return [c for c in sv.class_descendants(root) if not sv.get_class(c).abstract]


DISPATCHED = set(concrete_descendants("FileObject")) | set(concrete_descendants("FileSet"))


def dispatch_table(root):
    base = {s.name for s in sv.class_induced_slots("DataFile" if root == "FileObject" else "FileSet") if s.required}
    rows = []
    for name in [c for _, _, cs in CLASS_GROUPS for c in cs if c in concrete_descendants(root)]:
        slots = sv.class_induced_slots(name)
        enc = next(s for s in slots if s.name == "encodingFormat")
        fmts = [enc.equals_string] if enc.equals_string else [a.equals_string for a in (enc.any_of or [])]
        fmt = "<br>".join(f"<code>{html.escape(x)}</code>" for x in fmts) or "<span class=muted>any media type</span>"
        extra = [s.alias or s.name for s in slots if s.required and s.name not in base]
        rows.append(
            f"<tr><td><a href='reference.html#{name}'><code>rddc:{name}</code></a></td>"
            f"<td>{html.escape(sv.get_class(name).description or '')}</td>"
            f"<td>{fmt}</td>"
            f"<td>{', '.join(f'<code>{e}</code>' for e in extra) or '<span class=muted>none</span>'}</td></tr>"
        )
    return (
        "<div class='table-wrap'><table><thead><tr><th>additionalType</th><th>Use for</th>"
        "<th>encodingFormat</th><th>Extra required fields</th></tr></thead><tbody>"
        + "".join(rows) + "</tbody></table></div>"
    )


def reference_page():
    toc = "".join(
        f"<li><a href='#{slug(g)}'>{g}</a></li>" for g, _, _ in CLASS_GROUPS
    )
    body = [
        "<h1>Schema reference</h1>",
        f"<p class='lede'>Every class in schema version <strong>{VERSION}</strong>, generated from "
        "<code>schema/rddc_sidecar.yaml</code>. Property keys are coloured by vocabulary, and their full IRI "
        "appears on hover. Inherited properties are included, so each class lists everything "
        "it accepts. Unlisted properties are rejected.</p>",
        "<h2 id='file-classes-at-a-glance'>File classes at a glance</h2>",
        "<p>Every file needs <code>@id</code>, <code>name</code>, <code>contentUrl</code>, <code>contentSize</code>, "
        "<code>encodingFormat</code>, <code>sha256</code> and <code>modality</code>. The class adds the fields below.</p>",
        dispatch_table("FileObject"),
        "<h2 id='file-set-classes-at-a-glance'>File set classes at a glance</h2>",
        "<p>Every file set needs <code>@id</code>, <code>name</code>, and <code>hasPart</code> or <code>includes</code> (or both).</p>",
        dispatch_table("FileSet"),
    ]
    for group, blurb, classes in CLASS_GROUPS:
        body.append(f"<h2 id='{slug(group)}'>{group}</h2><p>{blurb}</p>")
        body.extend(class_section(c) for c in classes)
    body.append(VALIDATOR_RULES)
    return "\n".join(body)


VALIDATOR_RULES = """
<h2 id="rules-beyond-json-schema">Rules beyond JSON Schema</h2>
<p>JSON Schema cannot express every rule. The <code>rddc-sidecar</code> validator checks these as well:</p>
<ul>
<li>Every <code>@id</code> is unique within the sidecar, and so is every subject identity
(<code>idSystem</code>, <code>identifierSystemUri</code>, <code>subjectId</code>).</li>
<li>Every reference resolves: <code>hasPart</code>, <code>about</code>, <code>indexOf</code>, <code>pairedWith</code>, <code>wasDerivedFrom</code>,
record set sources and keys, and each file's <code>subjectIds</code> (against the subject table).</li>
<li>The subject table is non-empty unless the batch is an <code>add</code> batch whose files all have <code>modality</code> <code>metadata</code>
(documentation only).</li>
<li><code>withdraw</code> and <code>restrict</code> batches list no data files, and every row of a consent batch has a <code>consentRef</code>.</li>
<li>File set <code>conformsTo</code> values come from the pinned list (FHIR R4, US Core 6.1, OMOP CDM 5.4, C-CDA 2.1).</li>
<li><code>directIdentifiersRemoved</code> is <code>true</code> unless <code>synthetic</code> is <code>true</code>.</li>
</ul>
"""


def vocab_page():
    body = [
        "<h1>Controlled vocabularies</h1>",
        f"<p class='lede'>Allowed values and formats for schema version <strong>{VERSION}</strong>. "
        "Validation uses the values defined by the version in <code>conformsTo</code>.</p>",
        "<h2 id='enumerations'>Enumerations</h2>",
    ]
    users = {}
    for sname, slot in sv.all_slots().items():
        if slot.range in sv.all_enums():
            users.setdefault(slot.range, []).append(slot.alias or sname)
    for name, enum in sv.all_enums().items():
        rows = "".join(
            f"<tr><td><code>{html.escape(v)}</code></td><td>{html.escape(pv.description or '')}</td></tr>"
            for v, pv in enum.permissible_values.items()
        )
        used = ", ".join(f"<code>{u}</code>" for u in sorted(users.get(name, [])))
        body.append(
            f"<section class='class' id='{name}'><h3>{name}</h3><p>{html.escape(enum.description or '')}</p>"
            f"<p class='meta'><span>Used by {used}</span></p>"
            f"<div class='table-wrap'><table><thead><tr><th>Value</th><th>Meaning</th></tr></thead><tbody>{rows}</tbody></table></div></section>"
        )
    body.append("<h2 id='value-types'>Value types</h2><p>Text formats checked with regular expressions.</p>")
    rows = "".join(
        f"<tr id='type-{n}'><td><code>{n}</code></td><td>{html.escape(t.description or '')}</td>"
        f"<td><code class='pattern'>{html.escape(t.pattern or '')}</code></td></tr>"
        for n, t in sv.schema.types.items()
    )
    body.append(f"<div class='table-wrap'><table><thead><tr><th>Type</th><th>Meaning</th><th>Pattern</th></tr></thead><tbody>{rows}</tbody></table></div>")
    return "\n".join(body)


# ---------------------------------------------------------------------------
# Page assembly
# ---------------------------------------------------------------------------
def slug(text):
    text = re.sub(r"<[^>]+>", "", text)
    return re.sub(r"[^a-z0-9]+", "-", html.unescape(text).lower()).strip("-")


def add_heading_ids(body):
    seen = set()

    def fix(m):
        level, attrs, inner = m.group(1), m.group(2), m.group(3)
        if "id=" in attrs:
            ident = re.search(r"id=['\"]([^'\"]+)", attrs).group(1)
        else:
            ident = slug(inner)
            while ident in seen:
                ident += "-x"
            attrs += f' id="{ident}"'
        seen.add(ident)
        return f"<h{level}{attrs}>{inner}</h{level}>"

    return re.sub(r"<h([23])([^>]*)>(.*?)</h\1>", fix, body, flags=re.S)


def page_toc(body):
    items = []
    for level, ident, inner in re.findall(r"<h([23])[^>]*id=['\"]([^'\"]+)['\"][^>]*>(.*?)</h\1>", body, flags=re.S):
        text = html.escape(html.unescape(re.sub(r"<[^>]+>", "", inner)).strip())
        items.append(f"<li class='l{level}'><a href='#{ident}'>{text}</a></li>")
    if len(items) > 40:
        items = [i for i in items if "class='l2'" in i]
    if len(items) < 2:
        return ""
    return "<nav class='toc' aria-label='On this page'><p>On this page</p><ul>" + "".join(items) + "</ul></nav>"


def sidebar(current):
    out = []
    for group, items in NAV:
        links = "".join(
            f"<li><a href='{f}'{' aria-current=\"page\"' if f == current else ''}>{t}</a></li>" for f, t in items
        )
        out.append(f"<div class='group'><p>{group}</p><ul>{links}</ul></div>")
    return "".join(out)


def prev_next(current):
    idx = [f for f, _ in PAGES].index(current)
    parts = []
    if idx > 0:
        f, t = PAGES[idx - 1]
        parts.append(f"<a class='prev' href='{f}'><span>Previous</span>{t}</a>")
    else:
        parts.append("<span></span>")
    if idx < len(PAGES) - 1:
        f, t = PAGES[idx + 1]
        parts.append(f"<a class='next' href='{f}'><span>Next</span>{t}</a>")
    return "<nav class='pager' aria-label='Pages'>" + "".join(parts) + "</nav>"


def search_entries(fname, title, body):
    entries = []
    chunks = re.split(r"(<h[23][^>]*id=['\"][^'\"]+['\"][^>]*>.*?</h[23]>)", body, flags=re.S)
    anchor, heading = "", title
    for chunk in chunks:
        m = re.match(r"<h[23][^>]*id=['\"]([^'\"]+)['\"][^>]*>(.*?)</h[23]>", chunk, flags=re.S)
        if m:
            anchor, heading = m.group(1), html.unescape(re.sub(r"<[^>]+>", "", m.group(2))).strip()
            continue
        text = re.sub(r"<pre.*?</pre>", " ", chunk, flags=re.S)
        text = html.unescape(re.sub(r"<[^>]+>", " ", text))
        text = re.sub(r"\s+", " ", text).strip()
        entries.append({"page": title, "heading": heading, "url": fname + (f"#{anchor}" if anchor else ""), "text": text[:600]})
    return entries


def render(fname, title, body, template, home=False):
    body = add_heading_ids(expand_directives(body))
    toc = "" if home else page_toc(body)
    pager = "" if home else prev_next(fname)
    out = (
        template.replace("{{title}}", html.escape(title))
        .replace("{{version}}", VERSION)
        .replace("{{sidebar}}", sidebar(fname))
        .replace("{{toc}}", toc)
        .replace("{{layout}}", "home" if home else "doc")
        .replace("{{pager}}", pager)
        .replace("{{content}}", body)
    )
    return out, body


# ---------------------------------------------------------------------------
# Recipe checks
# ---------------------------------------------------------------------------
def check_recipes():
    schema = json.load(open(os.path.join(GEN, "rddc_sidecar.schema.json")))
    v = jsonschema.validators.validator_for(schema)(schema)
    problems = []
    for path in sorted(glob.glob(os.path.join(SITE, "recipes", "*.json"))):
        doc = json.load(open(path))
        doc = {"@context": CONTEXT, **doc}
        errors = list(v.iter_errors(doc))
        if errors:
            problems.append(f"{os.path.basename(path)} should be valid: {errors[0].json_path}: {errors[0].message[:200]}")
    for path in sorted(glob.glob(os.path.join(SITE, "recipes", "mistakes", "*.json"))):
        doc = {"@context": CONTEXT, **json.load(open(path))}
        if v.is_valid(doc):
            problems.append(f"mistakes/{os.path.basename(path)} should be invalid but passes")
    if problems:
        raise SystemExit("recipe check failed:\n  " + "\n  ".join(problems))


def main():
    out = sys.argv[1] if len(sys.argv) > 1 else os.path.join(SITE, "dist")
    check_recipes()
    if os.path.exists(out):
        shutil.rmtree(out)
    shutil.copytree(os.path.join(SITE, "assets"), os.path.join(out, "assets"))
    dl = os.path.join(out, "downloads")
    os.makedirs(os.path.join(dl, "examples"))
    os.makedirs(os.path.join(dl, "recipes"))
    for f in glob.glob(os.path.join(ROOT, "examples", "*.json")):
        shutil.copy(f, os.path.join(dl, "examples"))
    for f in glob.glob(os.path.join(SITE, "recipes", "*.json")):
        doc = json.load(open(f))
        if "@id" in doc:  # a sidecar: embed the context so the download is a complete document
            doc = {"@context": CONTEXT, **doc}
        json.dump(doc, open(os.path.join(dl, "recipes", os.path.basename(f)), "w"), indent=2)
    shutil.copy(SCHEMA, dl)
    for f in glob.glob(os.path.join(GEN, "*")):
        shutil.copy(f, dl)
    shutil.copy(os.path.join(ROOT, "schema", "croissant-1.1-context.json"), dl)

    template = open(os.path.join(SITE, "template.html")).read()
    index = []
    for fname, title in PAGES:
        if fname == "reference.html":
            body = reference_page()
        elif fname == "vocabularies.html":
            body = vocab_page()
        else:
            body = open(os.path.join(SITE, "pages", fname)).read()
        body = body.replace("{{version}}", VERSION)
        page, rendered = render(fname, title, body, template, home=fname == "index.html")
        open(os.path.join(out, fname), "w").write(page)
        index.extend(search_entries(fname, title, rendered))
    json.dump(index, open(os.path.join(out, "assets", "search-index.json"), "w"))
    # The presentation is a standalone HTML file with embedded styles and script.
    # Its code excerpts are kept in the source file (so it renders when opened
    # directly) and refreshed here from the example JSON and the schema.
    slides_path = os.path.join(SITE, "slides.html")
    with open(slides_path) as source:
        original = source.read()
    slides = original
    excerpts = [("slide-example", name, highlight_json(text)) for name, text in slide_example().items()]
    excerpts += [("slide-linkml", name, highlight_yaml(text)) for name, text in slide_linkml().items()]
    for kind, name, body in excerpts:
        block = re.compile(r"(<!-- %s:%s -->).*?(<!-- /%s -->)" % (kind, name, kind), re.S)
        if not block.search(slides):
            sys.exit(f"site/slides.html: missing <!-- {kind}:{name} --> block")
        slides = block.sub(lambda m: m.group(1) + body + m.group(2), slides)
    if slides != original:
        with open(slides_path, "w") as target:
            target.write(slides)
        print("refreshed the code excerpts in site/slides.html")
    slides = slides.replace("{{version}}", VERSION)
    with open(os.path.join(out, "slides.html"), "w") as target:
        target.write(slides)
    open(os.path.join(out, ".nojekyll"), "w").close()
    print(f"built {len(PAGES)} pages and slide deck into {os.path.relpath(out, ROOT)}")


if __name__ == "__main__":
    main()
