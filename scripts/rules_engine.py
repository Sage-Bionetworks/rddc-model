"""Shared code for the processing rules: load a rule set, the model release it pins and
a source register; check the names the rules use; export facts and run the ASP programs
in rules/ with clingo.

Used by scripts/check_rules.py (static verification) and scripts/orchestrate.py (the
orchestrator). The reasoning is in rules/engine.lp, rules/route.lp and rules/plan.lp;
this module only translates between YAML/JSON and facts.
"""

import json
import os
import re
import subprocess
import tempfile
from collections import deque
from itertools import product

import clingo
import yaml
from linkml_runtime.utils.schemaview import SchemaView

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
RULES_DIR = os.path.join(ROOT, "rules")
MODULES = ("core.yaml", "data.yaml", "rddc_sidecar.yaml", "processing.yaml")
SIDECAR_VERSION = re.compile(r"^https://w3id\.org/rddc/sidecar/(\d+\.\d+\.\d+)$")
ASSAY_ENUMS = ("GenomicsAssayEnum", "ImagingAssayEnum", "SensorAssayEnum")
BATCH_LEVEL = {"withdraw", "restrict"}
FLAG_SOURCES = {"flag_true", "flag_false"}
# Kinds of workflow that record a finding or decision and write no data.
NO_DATA_KINDS = {"expert_review", "confirm"}


# --- the pinned release ---------------------------------------------------------

class Release:
    """The model release a rule set pins: its classes, flags, fields and enum values."""

    def __init__(self, tag):
        self.tag = tag
        self.note, self.errors = None, []
        self._tmp = None
        schema_dir = self._schema_dir(tag)
        self.versions = {m: yaml.safe_load(open(os.path.join(schema_dir, m))).get("version")
                         for m in MODULES if os.path.exists(os.path.join(schema_dir, m))}
        for m, v in self.versions.items():
            if "v" + str(v) != tag:
                self.errors.append(f"{m} has version {v}, but the rule set pins {tag}")
        sv = SchemaView(os.path.join(schema_dir, "rddc_sidecar.yaml"))
        self.data_classes = set(sv.class_descendants("DataFile"))
        self.concrete = sorted(c for c in self.data_classes if not sv.get_class(c).abstract)
        self.file_set_classes = set(sv.class_descendants("FileSet"))
        self.ancestors = {c: set(sv.class_ancestors(c)) for c in self.data_classes | self.file_set_classes}
        self.annotations = {
            c: {k: a.value for k, a in sv.get_class(c).annotations.items()} for c in self.data_classes}
        self.annotation_keys = {k for anns in self.annotations.values() for k in anns}
        self.flags = set(sv.class_slots("SensitivityDeclaration")) | set(sv.class_slots("FileSensitivity"))
        self.interactions = set(sv.get_enum("InteractionEnum").permissible_values)
        self.techniques = {v for e in ASSAY_ENUMS for v in sv.get_enum(e).permissible_values}
        self.batch_slots = set(sv.class_slots("Sidecar"))
        self.file_set_slots = {s for c in self.file_set_classes for s in sv.class_slots(c)}
        # The pinned conformsTo values are listed in the FileSet conformsTo description.
        self.pinned_standards = sv.induced_slot("conformsTo", "FileSet").description or ""
        # Source register fields and their enum values, from processing.yaml.
        pv = SchemaView(os.path.join(schema_dir, "processing.yaml"))
        self.register_fields = {}
        for s in pv.class_slots("SourceRegisterEntry"):
            rng = pv.induced_slot(s, "SourceRegisterEntry").range
            enum = pv.get_enum(rng) if rng in pv.all_enums() else None
            self.register_fields[s] = set(enum.permissible_values) if enum else None

    def _schema_dir(self, tag):
        found = subprocess.run(["git", "-C", ROOT, "rev-parse", "-q", "--verify", f"refs/tags/{tag}"],
                               capture_output=True, text=True).returncode == 0
        if not found:
            self.note = f"tag {tag} does not exist yet; using the working tree's schema/"
            return os.path.join(ROOT, "schema")
        self._tmp = tempfile.TemporaryDirectory()
        archive = subprocess.run(["git", "-C", ROOT, "archive", tag, "schema"], capture_output=True, check=True)
        subprocess.run(["tar", "-x", "-C", self._tmp.name], input=archive.stdout, check=True)
        return os.path.join(self._tmp.name, "schema")

    def is_a(self, cls, ancestor):
        return ancestor in self.ancestors.get(cls, ())

    def modality(self, cls):
        return self.annotations[cls].get("modality")


def load_rules(path=None):
    return yaml.safe_load(open(path or os.path.join(RULES_DIR, "rules.yaml")))


def register_entry(register, source_id):
    return next((s for s in register.get("sources", []) if s["sourceId"] == source_id), None)


def sidecar_release(sidecar):
    """The model release tag a sidecar declares in conformsTo, or None."""
    for uri in sidecar.get("conformsTo", []):
        m = SIDECAR_VERSION.match(uri)
        if m:
            return "v" + m.group(1)
    return None


# --- name and reference checks ----------------------------------------------------

def conditions(rules):
    """Every condition in the rule set, with where it is."""
    for w in rules.get("workflows", []):
        if "consumes" in w:
            yield f"workflow {w['id']}", w["consumes"] or {}
    for kind in ("targets", "obligations", "prohibitions"):
        for r in rules.get(kind, []):
            yield f"{kind[:-1]} {r['id']}", r.get("when") or {}


def register_tests(rules):
    """(where, field, values) for every register field and value the rules read."""
    for where, c in conditions(rules):
        for t in c.get("sourceFacts") or []:
            yield where, t["field"], (t.get("anyOf") or []) + (t.get("noneOf") or [])
    for p in rules.get("properties", []):
        for src in p.get("derivedFrom", []):
            if src["source"] == "register":
                yield f"property {p['id']}", src.get("key"), src.get("anyOf") or []


def name_errors(rules, rel):
    """Names the rule set uses that do not exist in the release or the rule set."""
    errs = list(rel.errors)
    ids = {k: [x["id"] for x in rules.get(k, [])] for k in ("properties", "standards", "zones", "workflows", "targets")}
    for k, names in ids.items():
        dupes = {n for n in names if names.count(n) > 1}
        errs += [f"duplicate {k[:-1]} id {n}" for n in sorted(dupes)]
    props, stds, zones, wfs = (set(ids[k]) for k in ("properties", "standards", "zones", "workflows"))
    kinds = {w["id"]: w["kind"] for w in rules.get("workflows", [])}
    from_release = {"data class", "file set class", "technique", "interaction", "flag", "annotation",
                    "register field"}

    def need(where, values, known, what):
        scope = f"release {rel.tag}" if what in from_release else "the rule set"
        errs.extend(f"{where}: {what} {v!r} is not in {scope}" for v in values or [] if v not in known)

    initial = [z["id"] for z in rules.get("zones", []) if z.get("initial")]
    if len(initial) != 1:
        errs.append(f"exactly one zone must be initial, found {initial}")
    errs += [f"zone {z['id']}: no location or cirroEnvironment" for z in rules.get("zones", [])
             if not z.get("initial") and "location" not in z and "cirroEnvironment" not in z]
    errs += cirro_errors(rules)
    for p in rules.get("properties", []):
        for src in p.get("derivedFrom", []):
            where = f"property {p['id']}"
            if src["source"] in FLAG_SOURCES:
                need(where, [src.get("key")], rel.flags, "flag")
                if src.get("key") == "synthetic":
                    errs.append(f"{where}: reads synthetic, but synthetic batches must follow the same routes (seed rule 10)")
            elif src["source"] == "annotation":
                need(where, [src.get("key")], rel.annotation_keys, "annotation")
            elif src["source"] == "data_class":
                need(where, src.get("classes"), rel.data_classes, "data class")
    for where, field, values in register_tests(rules):
        need(where, [field], rel.register_fields, "register field")
        known = rel.register_fields.get(field)
        if known is not None:
            errs.extend(f"{where}: {v!r} is not a value of register field {field} in release {rel.tag}"
                        for v in values if v not in known)
    for s in rules.get("standards", []):
        need(f"standard {s['id']}", s["classes"], rel.data_classes, "data class")
        if s["url"] not in rel.pinned_standards:
            errs.append(f"standard {s['id']}: {s['url']} is not a pinned conformsTo value in release {rel.tag}")
    for where, c in conditions(rules):
        need(where, c.get("classes"), rel.data_classes, "data class")
        need(where, c.get("standards"), stds, "standard")
        need(where, c.get("anyProperties"), props, "property")
        need(where, c.get("noProperties"), props, "property")
        need(where, c.get("fileSetClasses"), rel.file_set_classes, "file set class")
        need(where, c.get("techniques"), rel.techniques, "technique")
        need(where, c.get("interactions"), rel.interactions, "interaction")
    for w in rules.get("workflows", []):
        where = f"workflow {w['id']}"
        need(where, [w["produces"]] if "produces" in w else [], rel.data_classes, "data class")
        need(where, [w["producesStandard"]] if "producesStandard" in w else [], stds, "standard")
        need(where, w.get("readsFrom"), zones, "zone")
        need(where, [w["writesTo"]] if "writesTo" in w else [], zones, "zone")
        need(where, w.get("coversZones"), zones, "zone")
        need(where, w.get("clears"), props, "property")
        need(where, w.get("sets"), props, "property")
        for p in w.get("parameters", []):
            ref = p.get("fromSidecar")
            if ref:
                scope, _, field = ref.partition(".")
                known = {"batch": rel.batch_slots, "fileSet": rel.file_set_slots}.get(scope)
                if known is None or field not in known:
                    errs.append(f"{where}: parameter {p['id']} reads {ref!r}, not a sidecar field in release {rel.tag}")
            if "fromSourceRegister" in p:
                need(f"{where}: parameter {p['id']}", [p["fromSourceRegister"]], rel.register_fields, "register field")
    for t in rules.get("targets", []):
        where = f"target {t['id']}"
        need(where, t.get("goalClasses"), rel.data_classes, "data class")
        need(where, [t["goalStandard"]] if "goalStandard" in t else [], stds, "standard")
        need(where, [t["goalZone"]], zones, "zone")
        need(where, t.get("goalNoProperties"), props, "property")
    for o in rules.get("obligations", []):
        need(f"obligation {o['id']}", o.get("beforeZones"), zones, "zone")
        need(f"obligation {o['id']}", o.get("beforeWorkflows"), wfs, "workflow")
    for h in rules.get("prohibitions", []):
        need(f"prohibition {h['id']}", h["zones"], zones, "zone")
    for r in rules.get("interactionRules", []):
        where = f"interaction rule {r['interaction']}"
        need(where, [r["interaction"]], rel.interactions, "interaction")
        need(where, [r["workflow"]], wfs, "workflow")
        if r["workflow"] in kinds and kinds[r["workflow"]] != r["interaction"]:
            errs.append(f"{where}: workflow {r['workflow']} has kind {kinds[r['workflow']]}")
    covered = {r["interaction"] for r in rules.get("interactionRules", [])}
    errs += [f"interaction {i} has no interaction rule" for i in sorted(BATCH_LEVEL - covered)]
    return errs


def cirro_errors(rules):
    """Cirro works on datasets in environments. A Cirro process other than an ingest reads
    only from zones that are Cirro environments, and only Cirro processes write data to
    them (an expert review or a confirmation records a finding and writes no data)."""
    environments = {z["id"] for z in rules.get("zones", []) if "cirroEnvironment" in z}
    errs = []
    for w in rules.get("workflows", []):
        if w["kind"] in BATCH_LEVEL:
            continue
        where = f"workflow {w['id']}"
        cirro = w["runner"] == "cirro"
        ingest = cirro and w.get("cirroExecutor") == "INGEST"
        if cirro and w["writesTo"] not in environments:
            errs.append(f"{where}: a Cirro process writes to zone {w['writesTo']}, which is not a Cirro environment")
        if not cirro and w["writesTo"] in environments and w["kind"] not in NO_DATA_KINDS:
            errs.append(f"{where}: a {w['runner']} writes to zone {w['writesTo']}, a Cirro environment")
        if cirro and not ingest:
            errs += [f"{where}: a Cirro process reads from zone {z}, which is not a Cirro environment (ingest first)"
                     for z in w["readsFrom"] if z not in environments]
        if ingest and any(z in environments for z in w["readsFrom"]):
            errs.append(f"{where}: an ingest reads from a Cirro environment")
        if (w.get("cirroExecutor") == "INGEST") != (w["kind"] == "ingest"):
            errs.append(f"{where}: kind ingest and Cirro executor INGEST go together")
    return errs


# --- facts ----------------------------------------------------------------------

def q(s):
    return '"' + str(s).replace("\\", "\\\\").replace('"', '\\"') + '"'


def prop_bits(rules):
    return {p["id"]: 1 << i for i, p in enumerate(rules.get("properties", []))}


def catalog_facts(rules, rel):
    bits = prop_bits(rules)
    out = [f"mask(0..{(1 << len(bits)) - 1})."]
    out += [f"prop({q(p)}, {b})." for p, b in bits.items()]
    for c, ancestors in rel.ancestors.items():
        out.append(f"class({q(c)}).")
        out += [f"isa({q(c)}, {q(a)})." for a in ancestors]
    out += [f"standard({q(s['id'])})." for s in rules.get("standards", [])]
    for z in rules.get("zones", []):
        out.append(f"zone({q(z['id'])}).")
        if z.get("initial"):
            out.append(f"initial({q(z['id'])}).")

    def cond(name, c):
        c = c or {}
        f = [f"cond({name})."]
        for slot, pred in (("classes", "c_class"), ("standards", "c_std"), ("anyProperties", "c_any"),
                           ("noProperties", "c_none"), ("fileSetClasses", "c_fileset"),
                           ("techniques", "c_tech"), ("interactions", "c_inter")):
            f += [f"{pred}({name}, {q(v)})." for v in c.get(slot) or []]
        for t in c.get("sourceFacts") or []:
            f += [f"c_src_any({name}, {q(t['field'])}, {q(v)})." for v in t.get("anyOf") or []]
            f += [f"c_src_none({name}, {q(t['field'])}, {q(v)})." for v in t.get("noneOf") or []]
        return f

    for w in rules.get("workflows", []):
        n = q(w["id"])
        out += [f"workflow({n}).", f"kind({n}, {q(w['kind'])}).", f"wprio({n}, {w.get('priority', 0)})."]
        if w["kind"] in BATCH_LEVEL:
            out += [f"covers({n}, {q(z)})." for z in w.get("coversZones", [])]
            continue
        cn = f"c(w, {n})"
        out += cond(cn, w.get("consumes")) + [f"consumes({n}, {cn})."]
        out += [f"reads({n}, {q(z)})." for z in w.get("readsFrom", [])]
        out.append(f"writes({n}, {q(w['writesTo'])}).")
        if "produces" in w:
            out.append(f"produces({n}, {q(w['produces'])}).")
        if "producesStandard" in w:
            out.append(f"produces_std({n}, {q(w['producesStandard'])}).")
        out += [f"clears({n}, {q(p)})." for p in w.get("clears", [])]
        out += [f"sets({n}, {q(p)})." for p in w.get("sets", [])]
    for t in rules.get("targets", []):
        n, cn = q(t["id"]), f"c(t, {q(t['id'])})"
        out += cond(cn, t["when"]) + [f"target({n}, {cn}, {t['priority']}).", f"goal_zone({n}, {q(t['goalZone'])})."]
        out += [f"goal_class({n}, {q(c)})." for c in t.get("goalClasses", [])]
        if "goalStandard" in t:
            out.append(f"goal_std({n}, {q(t['goalStandard'])}).")
        out += [f"goal_none({n}, {q(p)})." for p in t.get("goalNoProperties", [])]
    for o in rules.get("obligations", []):
        n, cn = q(o["id"]), f"c(o, {q(o['id'])})"
        out += cond(cn, o["when"]) + [f"obligation({n}, {cn}, {q(o['requiredKind'])})."]
        out += [f"before_zone({n}, {q(z)})." for z in o.get("beforeZones", [])]
        out += [f"before_wf({n}, {q(w)})." for w in o.get("beforeWorkflows", [])]
    for h in rules.get("prohibitions", []):
        n, cn = q(h["id"]), f"c(h, {q(h['id'])})"
        out += cond(cn, h["when"]) + [f"prohibition({n}, {cn})."]
        out += [f"prohibited({n}, {q(z)})." for z in h["zones"]]
    for r in rules.get("interactionRules", []):
        out.append(f"interaction_rule({q(r['interaction'])}, {q(r['workflow'])}).")
    return "\n".join(out)


def profile_facts(name, prof):
    """prof: fileSetClass, techniques, interaction, and register {field: [values]}."""
    n = q(name)
    out = [f"profile({n})."]
    if prof.get("fileSetClass"):
        out.append(f"p_fileset({n}, {q(prof['fileSetClass'])}).")
    out += [f"p_tech({n}, {q(t)})." for t in prof.get("techniques", ())]
    if prof.get("interaction"):
        out.append(f"p_inter({n}, {q(prof['interaction'])}).")
    for field, values in sorted(prof.get("register", {}).items()):
        out += [f"p_src({n}, {q(field)}, {q(v)})." for v in values]
    return out


def state_term(cls, std, zone, mask):
    return f"s({q(cls)}, {q(std) if std else 'none'}, {q(zone)}, {mask})"


def start_fact(profile, cls, std, mask):
    return f"start({q(profile)}, {q(cls)}, {q(std) if std else 'none'}, {mask})."


def class_props(rules, rel, cls):
    """Properties the class makes true (forced), and those the sidecar flags decide (free)."""
    forced, free = set(), set()
    for p in rules.get("properties", []):
        for src in p.get("derivedFrom", []):
            if src["source"] == "annotation" and rel.annotations[cls].get(src["key"]) == "true":
                forced.add(p["id"])
            elif src["source"] == "data_class" and any(rel.is_a(cls, c) for c in src.get("classes", [])):
                forced.add(p["id"])
            elif src["source"] in FLAG_SOURCES:
                free.add(p["id"])
    return forced, free - forced


def register_props(rules, rel, register, cls):
    """Properties the source register makes true for a file of this class.
    register: {field: [values]}; a missing field counts as matching."""
    out = set()
    for p in rules.get("properties", []):
        for src in p.get("derivedFrom", []):
            if src["source"] == "register":
                values = register.get(src["key"])
                if not values or set(values) & set(src.get("anyOf") or []):
                    out.add(p["id"])
            elif src["source"] == "modality_not_registered":
                if rel.modality(cls) not in (register.get("modalities") or []):
                    out.add(p["id"])
    return out


def class_standards(rules, rel, cls):
    return [s["id"] for s in rules.get("standards", []) if any(rel.is_a(cls, c) for c in s["classes"])]


OTHER = "(another value)"


def register_options(rules):
    """For each register field the rules read, one value per distinct behaviour.

    Rules only test whether a field's values are in listed sets, so two values that are
    in the same sets behave the same, and one stands for both. The candidates are each
    listed value, an unlisted value (OTHER) and a missing field (None): they differ
    because a register-derived property counts a missing field as matching."""
    tests = {}
    for _, c in conditions(rules):
        for t in c.get("sourceFacts") or []:
            tests.setdefault(t["field"], []).append(("cond", set(t.get("anyOf") or []), set(t.get("noneOf") or [])))
    for p in rules.get("properties", []):
        for src in p.get("derivedFrom", []):
            if src["source"] == "register":
                tests.setdefault(src["key"], []).append(("prop", set(src.get("anyOf") or []), set()))
    out = {}
    for field, ts in tests.items():
        listed = sorted(set().union(*(a | n for _, a, n in ts)))
        seen, reps = set(), []
        for v in listed + [OTHER, None]:
            sig = tuple((v is None and kind == "prop") or v in a for kind, a, _ in ts) + \
                tuple(v in n for _, _, n in ts)
            if sig not in seen:
                seen.add(sig)
                reps.append(v)
        out[field] = reps
    return out


def verification_deposits(rules, rel):
    """Facts for every kind of deposit that matters to the rules.

    A profile takes each file set class, technique and interaction the rules mention
    (or none), and for each register field the rules read, one value per distinct
    behaviour (see register_options). Within a profile, each concrete class is deposited with each standard it can
    conform to (or none) and each combination of flag-decided properties; whether its
    modality is registered is decided both ways."""
    used = {k: set() for k in ("fileSetClasses", "techniques", "interactions")}
    for _, c in conditions(rules):
        for k in used:
            used[k] |= set(c.get(k) or [])
    fields = register_options(rules)
    modality_props = {p["id"] for p in rules.get("properties", [])
                      if any(s["source"] == "modality_not_registered" for s in p.get("derivedFrom", []))}
    names = sorted(fields)
    bits = prop_bits(rules)
    out, profiles = [], {}
    dims = product([None] + sorted(used["fileSetClasses"]), [()] + [(t,) for t in sorted(used["techniques"])],
                   [None] + sorted(used["interactions"]), product(*[fields[f] for f in names]))
    for i, (fs, tech, inter, values) in enumerate(dims):
        register = {f: [v] for f, v in zip(names, values) if v is not None}
        prof = {"fileSetClass": fs, "techniques": tech, "interaction": inter, "register": register}
        name = f"p{i}"
        profiles[name] = prof
        out += profile_facts(name, prof)
        for cls in rel.concrete:
            forced, free = class_props(rules, rel, cls)
            # Register-derived properties, except the modality one, which goes both ways.
            forced |= register_props(rules, rel, dict(register, modalities=[rel.modality(cls)]), cls)
            free = sorted(free | modality_props)
            for std in [None] + class_standards(rules, rel, cls):
                for on in product((0, 1), repeat=len(free)):
                    present = forced | {p for p, x in zip(free, on) if x}
                    out.append(start_fact(name, cls, std, sum(bits[p] for p in present)))
    return "\n".join(out), profiles


def describe_deposit(prof, state, rules):
    _, cls, std, _, mask = state
    parts = [cls]
    if std != "none":
        parts.append(f"conforming to {std}")
    if prof.get("fileSetClass"):
        parts.append(f"in a {prof['fileSetClass']}")
    if prof.get("techniques"):
        parts.append(f"technique {prof['techniques'][0]}")
    if prof.get("interaction"):
        parts.append(f"in a {prof['interaction']} batch")
    reg = ", ".join(f"{f}={v[0]}" for f, v in sorted(prof.get("register", {}).items()))
    parts.append(f"from a source with {reg or 'none of the register values the rules read'}")
    present = [p for p, b in prop_bits(rules).items() if mask & b]
    parts.append("with " + (", ".join(present) if present else "no properties"))
    return " ".join(parts)


# --- sidecars -------------------------------------------------------------------

def local(name):
    return name.split(":", 1)[1] if ":" in name else name


def glob_regex(pattern):
    """A file set glob as a regex: ** matches any number of path segments."""
    out, i = "", 0
    while i < len(pattern):
        if pattern.startswith("**/", i):
            out, i = out + "(?:.*/)?", i + 3
        elif pattern.startswith("**", i):
            out, i = out + ".*", i + 2
        else:
            c = pattern[i]
            out += "[^/]*" if c == "*" else "[^/]" if c == "?" else re.escape(c)
            i += 1
    return re.compile(out + r"\Z")


def in_set(file_set, d):
    """Whether a file is a member of a file set, by hasPart or by its globs."""
    if any(p["@id"] == d["@id"] for p in file_set.get("hasPart", [])):
        return True
    path = d.get("contentUrl") or d.get("name") or ""
    return (any(glob_regex(g).match(path) for g in file_set.get("includes", []))
            and not any(glob_regex(g).match(path) for g in file_set.get("excludes", [])))


def entry_facts(entry, rules):
    """The register values the rules read, as {field: [values]}."""
    fields = {f for _, f, _ in register_tests(rules)} | {"modalities"}
    out = {}
    for f in sorted(fields):
        v = entry.get(f)
        if v is not None:
            out[f] = v if isinstance(v, list) else [v]
    return out


def sidecar_files(sidecar, entry, rules, rel):
    """The data files of a sidecar, with what the rules need to know about each."""
    dist = sidecar.get("distribution", [])
    sets = {d["@id"]: d for d in dist if d.get("@type") == "cr:FileSet"}
    member_of = {}
    for d in dist:
        hits = [sid for sid, s in sets.items() if d.get("@type") == "cr:FileObject" and in_set(s, d)]
        if len(hits) > 1:
            raise ValueError(f"{d['@id']} is in more than one file set: {hits}")
        if hits:
            member_of[d["@id"]] = hits[0]
    batch_sens = sidecar.get("sensitivity", {})
    register = entry_facts(entry, rules)
    bits = prop_bits(rules)
    base = sidecar.get("url", "").rstrip("/") + "/"
    files = []
    for d in dist:
        if d.get("@type") != "cr:FileObject":
            continue
        cls = local(d["additionalType"])
        fs_id = member_of.get(d["@id"])
        fs = sets.get(fs_id, {})
        sens = dict(batch_sens, **d.get("sensitivity", {}))
        present = class_props(rules, rel, cls)[0] | register_props(rules, rel, register, cls)
        for p in rules.get("properties", []):
            for src in p.get("derivedFrom", []):
                # A missing flag means unknown, which counts as present.
                if src["source"] == "flag_true" and sens.get(src["key"], True) is True:
                    present.add(p["id"])
                elif src["source"] == "flag_false" and sens.get(src["key"], False) is False:
                    present.add(p["id"])
        std = next((s["id"] for s in rules.get("standards", [])
                    if s["url"] in fs.get("conformsTo", []) and s["id"] in class_standards(rules, rel, cls)), None)
        tech = d.get("measurementTechnique", [])
        files.append({
            "id": d["@id"], "class": cls, "standard": std,
            "mask": sum(bits[p] for p in present),
            "fileSet": fs_id, "location": base + d.get("contentUrl", ""),
            "profile": {"fileSetClass": local(fs["additionalType"]) if fs else None,
                        "techniques": tuple(tech if isinstance(tech, list) else [tech]),
                        "interaction": sidecar.get("interaction"), "register": register},
        })
    return files


def file_facts(files):
    """Facts for the files of a batch: a profile per distinct profile, the starting state
    of each file, and file(X, Profile) to tie each file to its profile."""
    names, out = {}, []
    for f in files:
        key = json.dumps(f["profile"], sort_keys=True, default=list)
        if key not in names:
            names[key] = f"b{len(names)}"
            out += profile_facts(names[key], f["profile"])
        out.append(start_fact(names[key], f["class"], f["standard"], f["mask"]))
        out.append(f"file({q(f['id'])}, {q(names[key])}, {q(f['class'])}, "
                   f"{q(f['standard']) if f['standard'] else 'none'}, {f['mask']}).")
    return "\n".join(out)


# --- solving --------------------------------------------------------------------

def solve(programs, facts, optimal=False, args=()):
    """Ground and solve; return the shown symbols of the model (or, with optimal=True,
    of every optimal model, so callers can detect ties)."""
    ctl = clingo.Control(["--warn=none", *args] + (["--opt-mode=optN", "0"] if optimal else []))
    for p in programs:
        ctl.load(os.path.join(RULES_DIR, p))
    ctl.add("base", [], facts)
    ctl.ground([("base", [])])
    models = []
    with ctl.solve(yield_=True) as handle:
        for m in handle:
            if not optimal or m.optimality_proven:
                models.append(list(m.symbols(shown=True)))
        result = handle.get()
    if optimal:
        return models
    if not result.satisfiable:
        raise RuntimeError("the rules program has no answer set")
    return models[-1]


def py(sym):
    """A clingo symbol as a Python value (strings, numbers, tuples for functions)."""
    if sym.type == clingo.SymbolType.String:
        return sym.string
    if sym.type == clingo.SymbolType.Number:
        return sym.number
    if not sym.arguments:
        return sym.name
    return (sym.name, *[py(a) for a in sym.arguments])


def by_name(symbols):
    out = {}
    for s in symbols:
        out.setdefault(s.name, []).append(tuple(py(a) for a in s.arguments))
    return out


# --- explaining -----------------------------------------------------------------

def mask_props(mask, rules):
    return [p for p, b in prop_bits(rules).items() if mask & b]


def state_text(state, rules):
    _, cls, std, zone, mask = state
    std = "" if std == "none" else f" ({std})"
    return f"{zone}: {cls}{std} [{', '.join(mask_props(mask, rules)) or 'no properties'}]"


def example_route(profile, state, steps, starts):
    """A deposit of the profile that reaches state, and a shortest route from it, as
    (start, [(workflow, state), ...])."""
    back = {}
    for p, a, w, b in steps:
        if p == profile:
            back.setdefault(b, []).append((w, a))
    origins = set(starts.get(profile, ()))
    nxt, todo = {state: None}, deque([state])
    while todo:
        b = todo.popleft()
        if b in origins:
            path, s = [], b
            while nxt[s]:
                w, s2 = nxt[s]
                path.append((w, s2))
                s = s2
            return b, path
        for w, a in back.get(b, []):
            if a not in nxt:
                nxt[a] = (w, b)
                todo.append(a)
    return state, []
