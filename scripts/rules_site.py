"""The processing configuration section of the documentation site.

Used by scripts/build_site.py. Everything here is generated from rules/rules.yaml and
the routes the rules engine finds (rules_engine.deposit_routes), so the pages always
describe the rules in this checkout:

- explorer_data(): every kind of deposit a reader can describe on the "Data trajectory"
  page, with its target and route (written to assets/data-trajectory.json);
- rules_page(): where each data class ends up (the targets map) and every rule as a
  sentence (rule cards), with what the checker proves;
- explorer_page(): the data trajectory page, which site/assets/data-trajectory.js fills in.
"""

import html
import json
import os
from itertools import product

from linkml_runtime.utils.schemaview import SchemaView

import rules_engine as E

# Destination groups of the targets map, in this order; each has a categorical slot.
DESTINATIONS = [
    ("normalized", "Reaches the normalized store"),
    ("deid_qc", "Stays in INTAKE (de-identification and QC environment)"),
    ("curation", "Held for a curator"),
]
RUNNER_LABEL = {"cirro": "Cirro", "container": "Container", "service": "Service"}


def esc(text):
    return html.escape(str(text), quote=True)


# --- explorer data ------------------------------------------------------------

def explorer_data(rules, rel):
    """Every deposit a reader can describe, and what happens to it.

    A deposit is a profile (file set class, technique, interaction, source register
    values: rules_engine.profile_dims), a data class with a standard, the sensitivity
    flags the rules read, and whether the source is registered for the class's
    modality. table[i] is the route of deposit i, numbered in that order (the page's
    script numbers them the same way)."""
    dims = E.profile_dims(rules)
    flags = E.flag_keys(rules)
    combos = [(c, s) for c in rel.concrete for s in [None] + E.class_standards(rules, rel, c)]
    keys, deposits = [], []
    for values in product(*[opts for _, opts in dims]):
        prof = E.profile_of(dims, values)
        for cls, std in combos:
            for bits in range(1 << len(flags)):
                fv = {k: bool(bits >> j & 1) for j, k in enumerate(flags)}
                for registered in (False, True):
                    mask = E.deposit_mask(rules, rel, cls, fv, prof["register"], registered)
                    deposits.append((prof, cls, std, mask))
    unique = list({json.dumps(d, sort_keys=True, default=list): d for d in deposits}.values())
    routed = dict(zip((json.dumps(d, sort_keys=True, default=list) for d in unique),
                      E.deposit_routes(rules, rel, unique)))
    # A route stores its workflows; the page replays their effects (class, standard,
    # zone, properties cleared and set) from "workflows", as rules/engine.lp does.
    route_ids, routes, table = {}, [], []
    for d in deposits:
        r = routed[json.dumps(d, sort_keys=True, default=list)]
        entry = [r["target"], r["start"][4], [w for w, _ in r["path"] or []], r["duties"],
                 r["release"], r["public"], int(r["ambiguous"]) + 2 * int(r["path"] is None)]
        key = json.dumps(entry)
        if key not in route_ids:
            route_ids[key] = len(routes)
            routes.append(entry)
        table.append(route_ids[key])
    sv = SchemaView(os.path.join(E.ROOT, "schema", "rddc_sidecar.yaml"))
    return {
        "ruleSet": rules["id"], "version": rules["version"], "release": rules["modelRelease"],
        # A flag's default is the value that leaves its property false.
        "flags": [{"key": k, "default": any(src["source"] == "flag_false" and src["key"] == k
                                            for p in rules.get("properties", []) for src in p.get("derivedFrom", [])),
                   "description": (sv.induced_slot(k, "SensitivityDeclaration").description or "")} for k in flags],
        "combos": [[c, s] for c, s in combos],
        "classes": [{"name": c, "modality": rel.modality(c)} for c in rel.concrete],
        "dims": [{"name": n, "options": [option_label(n, v) for v in opts]} for n, opts in dims],
        "standards": {s["id"]: s.get("description", s["id"]) for s in rules.get("standards", [])},
        "properties": [[p["id"], p.get("description", "")] for p in rules.get("properties", [])],
        "initialZone": next(z["id"] for z in rules["zones"] if z.get("initial")),
        "workflows": {w["id"]: {k: w[k] for k in ("runner", "cirroExecutor", "kind", "description", "produces",
                                                   "producesStandard", "readsFrom", "writesTo", "clears", "sets", "recordsTo",
                                                   "pipelineVersion")
                                if k in w}
                      for w in rules["workflows"]},
        "governance": {"label": "GOVERN", "description": module_description("GOVERN"),
                       "records": sorted({w["recordsTo"] for w in rules["workflows"] if w.get("recordsTo")})},
        "zoneList": [{k: z[k] for k in ("id", "description", "module", "initial", "cirroEnvironment") if k in z}
                     for z in rules["zones"]],
        "targets": {t["id"]: {"sentence": plain(target_sentence(t, rules)), "note": t.get("description", ""),
                              "zone": t["goalZone"]} for t in rules["targets"]},
        "obligations": {o["id"]: {"sentence": plain(obligation_sentence(o, rules)), "note": o.get("description", "")}
                        for o in rules.get("obligations", [])},
        "zones": {z["id"]: z.get("description", "") for z in rules["zones"]},
        "routeFields": ["target", "startMask", "workflows", "duties", "release", "public", "flags"],
        "routes": routes, "table": table,
    }


def module_description(module):
    """A platform module's description, from ModuleEnum in schema/processing.yaml."""
    pv = SchemaView(os.path.join(E.ROOT, "schema", "processing.yaml"))
    pv_value = pv.get_enum("ModuleEnum").permissible_values.get(module)
    return " ".join((pv_value.description or "").split()) if pv_value else ""


def option_label(dim, value):
    if value is None:
        label = "not set" if dim.startswith("register:") else "none"
    elif value == E.OTHER:
        label = "another value"
    else:
        label = str(value)
    return {"value": value, "label": label}


def lookup(data, cls, std, flags, registered, profile_values):
    """The route of one deposit, numbered as explorer_data numbers them, as a dict
    with the states after each step replayed from the workflows' effects."""
    p = 0
    for d, v in zip(data["dims"], profile_values):
        p = p * len(d["options"]) + [o["value"] for o in d["options"]].index(v)
    combo = data["combos"].index([cls, std])
    bits = sum(1 << j for j, f in enumerate(data["flags"]) if flags.get(f["key"]))
    i = ((p * len(data["combos"]) + combo) * (1 << len(data["flags"])) + bits) * 2 + int(registered)
    target, mask, workflows, duties, release, public, flag = data["routes"][data["table"][i]]
    props = [pid for j, (pid, _) in enumerate(data["properties"]) if mask >> j & 1]
    state, steps = [cls, std or "none", props], []
    for w in workflows:
        wf = data["workflows"][w]
        state = [wf.get("produces", state[0]), wf.get("producesStandard", state[1]),
                 [x for x in state[2] if x not in wf.get("clears", [])] + [x for x in wf.get("sets", []) if x not in state[2]]]
        steps.append([w, wf["writesTo"], state[0], state[1], state[2]])
    return {"target": target, "start": props, "steps": steps, "duties": duties, "release": release,
            "public": public, "ambiguous": bool(flag & 1), "noRoute": bool(flag & 2)}


# --- plain language -------------------------------------------------------------

def code(name, title=""):
    t = f" title='{esc(title)}'" if title else ""
    return f"<code{t}>{esc(name)}</code>"


def soft(name):
    """A name with break opportunities at camelCase humps and after underscores, so it
    wraps between words in narrow columns: Clinical<wbr>Document<wbr>File."""
    import re
    return re.sub(r"(?<=[a-z0-9])(?=[A-Z])|(?<=_)", "<wbr>", esc(name))


def scode(name, title=""):
    t = f" title='{esc(title)}'" if title else ""
    return f"<code{t}>{soft(name)}</code>"


def join_or(items, word="or"):
    items = list(items)
    if len(items) <= 1:
        return "".join(items)
    return ", ".join(items[:-1]) + f" {word} " + items[-1]


def condition_text(cond, rules):
    """A condition as a phrase, e.g. 'FhirFile files conforming to FHIR R4, without biometric'."""
    cond = cond or {}
    props = {p["id"]: p.get("description", "") for p in rules.get("properties", [])}
    stds = {s["id"]: s.get("description", s["id"]) for s in rules.get("standards", [])}
    prop = lambda p: code(p, props.get(p, ""))
    head = (join_or(code(c) for c in cond["classes"]) + " files") if cond.get("classes") else "any file"
    parts = []
    if cond.get("standards"):
        parts.append("conforming to " + join_or(esc(stds.get(s, s)) for s in cond["standards"]))
    if cond.get("fileSetClasses"):
        parts.append("in a " + join_or(code(f) for f in cond["fileSetClasses"]) + " file set")
    if cond.get("anyProperties"):
        parts.append("with " + join_or(prop(p) for p in cond["anyProperties"]))
    if cond.get("noProperties"):
        parts.append("without " + join_or((prop(p) for p in cond["noProperties"]), "or"))
    if cond.get("techniques"):
        parts.append("measured by " + join_or(code(t) for t in cond["techniques"]))
    if cond.get("interactions"):
        parts.append("in a " + join_or(code(i) for i in cond["interactions"]) + " batch")
    for t in cond.get("sourceFacts") or []:
        if t.get("anyOf"):
            parts.append(f"from a source whose {code(t['field'])} is " + join_or(code(v) for v in t["anyOf"]))
        if t.get("noneOf"):
            parts.append(f"from a source whose {code(t['field'])} is not " + join_or(code(v) for v in t["noneOf"]))
    if not parts:
        return head
    # "any file with x", but "FhirFile files, conforming to FHIR R4, without x".
    return head + (" " if not cond.get("classes") else ", ") + ", ".join(parts)


def subject(cond, rules):
    """A condition as the subject of a sentence: capitalised, and followed by a comma
    when it has qualifiers, so the verb reads clearly."""
    text = condition_text(cond, rules)
    if text.startswith("any"):
        text = "A" + text[1:]
    qualified = any((cond or {}).get(k) for k in ("standards", "fileSetClasses", "anyProperties", "noProperties",
                                                   "techniques", "interactions", "sourceFacts"))
    return text + ("," if qualified and (cond or {}).get("classes") else "")


def runner_badge(w):
    label = RUNNER_LABEL.get(w["runner"], w["runner"])
    if w.get("cirroExecutor"):
        label += f" · {w['cirroExecutor']}"
    return f"<span class='pr-runner pr-runner-{esc(w['runner'])}'>{esc(label)}</span>"


def workflow_chip(wid, rules):
    w = next(x for x in rules["workflows"] if x["id"] == wid)
    return (f"<span class='pr-step' title='{esc(w.get('description', ''))}'>"
            f"<a href='#wf-{esc(wid)}'>{soft(wid)}</a>"
            f"<small>{esc(RUNNER_LABEL.get(w['runner'], w['runner']))} · v{esc(w['pipelineVersion'])}</small></span>")


def route_html(steps, rules):
    if not steps:
        return "<span class='muted'>nothing to run</span>"
    return "<span class='pr-arrow' aria-hidden='true'>→</span>".join(workflow_chip(w, rules) for w in steps)


# --- the rules page ---------------------------------------------------------------

def typical_deposit(rules, rel, data, cls):
    """The deposit the targets map shows for a class: its first standard, the file set
    class a rule pairs with it, flags all off except directIdentifiersRemoved, the
    modality registered, and register values no rule singles out."""
    stds = E.class_standards(rules, rel, cls)
    std = stds[0] if stds else None
    values = []
    for d in data["dims"]:
        opts = [o["value"] for o in d["options"]]
        if d["name"] == "fileSetClass":
            paired = [f for _, c in E.conditions(rules) for f in c.get("fileSetClasses") or []
                      if any(rel.is_a(cls, k) for k in c.get("classes") or [])]
            values.append(paired[0] if paired and paired[0] in opts else None)
        elif d["name"].startswith("register:"):
            values.append(E.OTHER if E.OTHER in opts else opts[0])
        else:
            values.append(opts[0])
    flags = {f["key"]: f["default"] for f in data["flags"]}
    return std, flags, True, values


def variations(rules, rel, data, cls, base):
    """What sends the class to another zone: one change at a time from the typical
    deposit. Returns [(change, zone)]."""
    std, flags, registered, values = base
    zone_of = {t["id"]: t["goalZone"] for t in rules["targets"]}
    found = []
    target = lookup(data, cls, std, flags, registered, values)["target"]
    out = found
    for f in data["flags"]:
        alt = dict(flags, **{f["key"]: not flags[f["key"]]})
        r = lookup(data, cls, std, alt, registered, values)
        if r["target"] != target:
            out.append((f"{scode(f['key'])} {'false' if flags[f['key']] else 'true'}", r["target"]))
    r = lookup(data, cls, std, flags, False, values)
    if r["target"] != target:
        out.append(("modality not registered for the source", r["target"]))
    if std is not None:
        r = lookup(data, cls, None, flags, registered, values)
        if r["target"] != target:
            out.append(("no standard declared", r["target"]))
    for i, d in enumerate(data["dims"]):
        if d["name"] == "fileSetClass" and values[i] is not None:
            alt = list(values)
            alt[i] = None
            r = lookup(data, cls, std, flags, registered, alt)
            if r["target"] != target:
                out.append((f"not in a {scode(values[i])} file set", r["target"]))
    here = zone_of[target]
    return [(text, zone_of[t]) for text, t in found if zone_of[t] != here]


def targets_map(rules, rel, data):
    """The targets map: one row per concrete class, grouped by destination. A change
    that sends every row outside a zone to that zone is said once, above the table."""
    targets = {t["id"]: t for t in rules["targets"]}
    rows = []
    for cls in rel.concrete:
        base = typical_deposit(rules, rel, data, cls)
        std, flags, registered, values = base
        r = lookup(data, cls, std, flags, registered, values)
        rows.append((cls, std, r, targets[r["target"]]["goalZone"], variations(rules, rel, data, cls, base)))
    common = []
    for change in {v for *_, vs in rows for v in vs}:
        text, zone = change
        if all(change in vs for _, _, _, z, vs in rows if z != zone):
            common.append(change)
    groups = {z: [] for z, _ in DESTINATIONS}
    for cls, std, r, zone, vs in rows:
        end = r["steps"][-1] if r["steps"] else [None, zone, cls, std or "none", r["start"]]
        end_std = data["standards"].get(end[3], "") if end[3] != "none" else ""
        ends = scode(end[2]) + (f" <span class='muted'>{esc(end_std)}</span>" if end_std else "")
        why = "".join(f"<li>{text} → {code(z)}</li>" for text, z in vs if (text, z) not in common)
        start = f" <span class='muted'>({esc(data['standards'][std])})</span>" if std else ""
        groups.setdefault(zone, []).append(
            f"<tr><td>{scode(cls)}{start}</td><td class='pr-route'>{route_html([s[0] for s in r['steps']], rules)}</td>"
            f"<td>{ends}</td><td>{'<ul class=pr-why>' + why + '</ul>' if why else '<span class=muted>—</span>'}</td></tr>")
    body = []
    for i, (zone, label) in enumerate(DESTINATIONS, 1):
        if not groups.get(zone):
            continue
        body.append(f"<tbody class='pr-dest pr-d{i}'><tr class='pr-group'><th colspan='4' scope='colgroup'>"
                    f"<span class='pr-swatch' aria-hidden='true'></span>{esc(label)} "
                    f"<span class='muted'>({len(groups[zone])} {'class' if len(groups[zone]) == 1 else 'classes'}, "
                    f"zone {code(zone)})</span></th></tr>" + "".join(groups[zone]) + "</tbody>")
    note = ""
    if common:
        items = "".join(f"<li>{text} sends it to {code(z)}.</li>" for text, z in sorted(common))
        note = f"<p>For every class below that is not already there:</p><ul>{items}</ul>"
    return (note + "<div class='table-wrap'><table class='pr-map'><colgroup><col class='pr-c-class'><col class='pr-c-route'>"
            "<col class='pr-c-end'><col class='pr-c-why'></colgroup><thead><tr><th scope='col'>Deposited as</th>"
            "<th scope='col'>Route (default)</th><th scope='col'>Normalization target</th>"
            "<th scope='col'>Goes elsewhere if (one change)</th></tr></thead>" + "".join(body) + "</table></div>")


def target_sentence(t, rules):
    stds = {s["id"]: s.get("description", s["id"]) for s in rules.get("standards", [])}
    goal = f"zone {code(t['goalZone'])}"
    if t.get("goalClasses"):
        goal += " as " + join_or(code(c) for c in t["goalClasses"])
    if t.get("goalStandard"):
        goal += f" conforming to {esc(stds.get(t['goalStandard'], t['goalStandard']))}"
    if t.get("goalNoProperties"):
        goal += ", without " + join_or(code(p) for p in t["goalNoProperties"])
    return f"{subject(t['when'], rules)} end{'s' if not (t['when'] or {}).get('classes') else ''} in {goal}."


def obligation_sentence(o, rules):
    before = []
    if o.get("beforeZones"):
        before.append("before entering " + zone_list(o["beforeZones"]))
    if o.get("beforeWorkflows"):
        before.append("before " + join_or(code(w) for w in o["beforeWorkflows"]) + " runs")
    article = "an" if o["requiredKind"][0] in "aeiou" else "a"
    return (f"{subject(o['when'], rules)} must go through {article} {code(o['requiredKind'])} workflow "
            f"{' or '.join(before)}.")


def plain(html_text):
    """A generated sentence without its markup, for the page's script."""
    import re
    return html.unescape(re.sub(r"<[^>]+>", "", html_text))


def note(rule):
    """A rule's description, when it has one: origin or rationale, not a restatement."""
    return f"<p class='muted'>{esc(rule['description'])}</p>" if rule.get("description") else ""


INTAKE_KINDS = {"deidentify", "qc", "record"}


def stage(w, zones):
    """Where a workflow acts: release (from the normalized store on); for workflows that
    take any data type, ingest (the one generic pipeline), check (a confirmation service)
    or hold (for a curator); for the rest, intake (de-identification, QC or record for one
    data type) or normalization (into the normalized store, or a transform in INTAKE);
    and batch (withdraw, restrict)."""
    if w["kind"] in E.BATCH_LEVEL:
        return "batch"
    if any(zones[z].get("module") not in ("INTAKE", None) for z in w["readsFrom"]):
        return "release"
    if not (w.get("consumes") or {}).get("classes"):
        return {"ingest": "ingest", "confirm": "check"}.get(w["kind"], "hold")
    if w["kind"] in INTAKE_KINDS:
        return "intake"
    return "normalization"


def pipelines_by_type(rules, rel):
    zones = {z["id"]: z for z in rules["zones"]}
    by_stage = {}
    for w in rules["workflows"]:
        by_stage.setdefault(stage(w, zones), []).append(w)
    rows = []
    for cls in rel.concrete:
        # A pipeline applies if it takes the class and does not refuse a property every
        # file of the class has (imaging_deid refuses biometric data, so not facial images).
        always = E.class_props(rules, rel, cls)[0]
        cells = []
        for st in ("intake", "normalization"):
            ws = [w for w in by_stage.get(st, []) if any(rel.is_a(cls, c) for c in w["consumes"]["classes"])
                  and not always & set(w["consumes"].get("noProperties") or [])]
            cells.append(" ".join(workflow_chip(w["id"], rules) for w in ws) or "<span class='muted'>—</span>")
        rows.append(f"<tr><td>{scode(cls)}</td><td>{cells[0]}</td><td>{cells[1]}</td></tr>")
    chips = lambda st: " ".join(workflow_chip(w["id"], rules) for w in by_stage.get(st, [])) or "none"
    return f"""<h2>Pipelines by data type</h2>
<p>De-identification, QC and normalization pipelines are specific to a data type, and each
has its own version. Only the ingest is generic: {chips('ingest')} brings files of any type
into INTAKE. Two steps are not pipelines and apply to any type: {chips('check')} confirms a
de-identification, and {chips('hold')} holds a file for a curator. After normalization, the
release steps are {chips('release')}.</p>
<div class="table-wrap"><table class="pr-map"><colgroup><col class="pr-c-class"><col style="width:38%"><col style="width:38%"></colgroup>
<thead><tr><th scope="col">Data class</th><th scope="col">In INTAKE (de-identification, QC, record)</th>
<th scope="col">Normalization</th></tr></thead><tbody>{''.join(rows)}</tbody></table></div>"""


def card(anchor, title, badge, sentence, extra=""):
    return (f"<div class='pr-card' id='{esc(anchor)}'><div class='pr-card-head'><strong>{title}</strong>{badge}</div>"
            f"<p>{sentence}</p>{extra}</div>")


def zone_list(zones):
    return join_or(code(z) for z in zones)


def rules_page(rules, rel, data, problems, deposits):
    stds = {s["id"]: s.get("description", s["id"]) for s in rules.get("standards", [])}
    zones = {z["id"]: z for z in rules["zones"]}
    out = [f"""<h1>Rules and targets</h1>
<p class="lede">What the RDDC does with each deposited file, generated from the rule set
{code(rules['id'])} {esc(rules['version'])}, which is written for model release {esc(rules['modelRelease'])}.</p>
<div class="note"><strong>Prototype for discussion.</strong> The workflows, Cirro process and environment ids,
locations and source register values are provisional. A class includes its subclasses
throughout. To see what happens to a particular file, use
<a href="data-trajectory.html">Data trajectory</a>.</div>"""]
    if problems:
        items = "".join(f"<li>{esc(p)}</li>" for p in problems)
        out.append(f"<div class='note pr-status pr-fail'><strong>The checker found problems in these rules:</strong><ul>{items}</ul></div>")
    else:
        out.append(f"""<div class="note pr-status pr-ok"><strong>Checked when this page was built.</strong>
Over {deposits:,} kinds of deposit (every data class, standard, combination of sensitivity
flags and source register values the rules read): every deposit has exactly one target
and a route to it; obligations and prohibitions hold on every route, not only the
default one; no route loops; and withdrawal and restriction reach every zone data can
reach.</div>""")

    out.append("""<h2>Where data ends up</h2>
<p>Each row is a data class deposited in the usual way: with its standard, no sensitivity
flags set except that direct identifiers are removed, from a source registered for its
modality. The last column lists single changes that send it elsewhere. Hover over a
workflow for what it does. Files of one file set with the same target move together, so a
file can take an extra step that another member of its set needs.</p>""")
    out.append(targets_map(rules, rel, data))

    out.append(pipelines_by_type(rules, rel))

    out.append("<h2>Targets</h2><p>Each file gets the first matching target, by priority (lowest first).</p>")
    for t in sorted(rules["targets"], key=lambda t: (t["priority"], t["id"])):
        out.append(card(f"target-{t['id']}", code(t["id"]), f"<span class='badge'>priority {t['priority']}</span>",
                        target_sentence(t, rules), note(t)))

    out.append("<h2>Obligations</h2><p>Duties that hold on every route a file can take.</p>")
    for o in rules.get("obligations", []):
        out.append(card(f"obligation-{o['id']}", code(o["id"]), "<span class='badge'>duty</span>",
                        obligation_sentence(o, rules), note(o)))
    out.append("<h2>Prohibitions</h2>")
    for h in rules.get("prohibitions", []):
        out.append(card(f"prohibition-{h['id']}", code(h["id"]), "<span class='badge'>never</span>",
                        f"{subject(h['when'], rules)} never enter{'s' if not (h['when'] or {}).get('classes') else ''} {zone_list(h['zones'])}.",
                        note(h)))

    out.append("""<h2>Workflows</h2><p>The workflow catalog. Cirro workflows run as Cirro processes in a
Cirro environment on Cirro datasets; container and service workflows read and write storage
locations.</p>""")
    for w in rules["workflows"]:
        rows = []
        if w["kind"] in E.BATCH_LEVEL:
            rows.append(("Acts on", f"the listed subjects' data in {zone_list(w.get('coversZones', []))}"))
        else:
            rows.append(("Accepts", condition_text(w.get("consumes"), rules)))
            rows.append(("Reads from → writes to", f"{zone_list(w['readsFrom'])} → {code(w['writesTo'])}"))
            effects = []
            if w.get("produces"):
                effects.append("becomes " + code(w["produces"]) +
                               (f" conforming to {esc(stds.get(w['producesStandard'], ''))}" if w.get("producesStandard") else ""))
            if w.get("clears"):
                effects.append("no longer has " + join_or((code(p) for p in w["clears"]), "or"))
            if w.get("sets"):
                effects.append("now has " + join_or((code(p) for p in w["sets"]), "and"))
            rows.append(("Effect", "; ".join(effects) or "<span class='muted'>moves the data; changes nothing the rules track</span>"))
        runs = code(w["cirroProcess"]) if w.get("cirroProcess") else code(w.get("pipeline", ""))
        if w.get("recordsTo"):
            rows.append(("Records to", f"GOVERN: {esc(w['recordsTo'])} <span class='muted'>(register entries; no data files)</span>"))
        rows.append(("Runs as", f"{runs} <span class='muted'>version {esc(w['pipelineVersion'])}</span>"))
        if w.get("parameters"):
            params = []
            for p in w["parameters"]:
                src = (esc(p["value"]) if "value" in p else f"sidecar {code(p['fromSidecar'])}" if "fromSidecar" in p
                       else f"source register {code(p['fromSourceRegister'])}")
                params.append(f"{code(p['id'])} ← {src}")
            rows.append(("Parameters", "<br>".join(params)))
        table = "<table class='pr-kv'>" + "".join(f"<tr><th scope='row'>{k}</th><td>{v}</td></tr>" for k, v in rows) + "</table>"
        out.append(card(f"wf-{w['id']}", code(w["id"]), runner_badge(w) + f"<span class='badge'>{esc(w['kind'])}</span>",
                        esc(w.get("description", "")), table))

    out.append("<h2>Data properties</h2><p>What the rules track about a file. A sensitivity flag that is not stated counts as present.</p>")
    rows = []
    for p in rules.get("properties", []):
        srcs = []
        for s in p.get("derivedFrom", []):
            srcs.append({"flag_true": lambda s: f"sidecar {code(s['key'])} is true or not stated",
                         "flag_false": lambda s: f"sidecar {code(s['key'])} is false or not stated",
                         "annotation": lambda s: f"class annotation {code(s['key'])}",
                         "data_class": lambda s: "class " + join_or(code(c) for c in s.get("classes", [])),
                         "register": lambda s: f"source register {code(s['key'])} is " + join_or(code(v) for v in s.get("anyOf", [])) + " or not set",
                         "modality_not_registered": lambda s: "the source is not registered for the file's modality"}[s["source"]](s))
        rows.append(f"<tr><td>{code(p['id'])}</td><td>{esc(p.get('description', ''))}</td>"
                    f"<td>{'<br>'.join(srcs) or '<span class=muted>set by workflows only</span>'}</td></tr>")
    out.append("<div class='table-wrap'><table><thead><tr><th>Property</th><th>Meaning</th><th>True at deposit if</th></tr></thead>"
               + "".join(rows) + "</table></div>")

    out.append("<h2>Zones</h2>")
    rows = []
    for z in zones.values():
        where = (f"Cirro environment {code(z['cirroEnvironment'])}" if z.get("cirroEnvironment")
                 else code(z["location"]) if z.get("location") else "the sidecar's url")
        rows.append(f"<tr><td>{code(z['id'])}</td><td>{esc(z.get('description', ''))}</td>"
                    f"<td>{esc(z.get('module', 'outside the platform'))}</td><td>{where}</td></tr>")
    out.append("<div class='table-wrap'><table><thead><tr><th>Zone</th><th>What it is</th><th>Module</th><th>Where</th></tr></thead>"
               + "".join(rows) + "</table></div>")
    return "\n".join(out)


def explorer_page(rules):
    return f"""<h1>Data trajectory</h1>
<p class="lede">Describe a file and its source, and see where the rules send it, through which
workflows, and why. Generated from the rule set {code(rules['id'])} {esc(rules['version'])}.</p>
<div class="note"><strong>Prototype for discussion.</strong> Workflows and register values are provisional.
A sensitivity flag left unstated in a sidecar counts as true. The route shown is the one the
orchestrator would choose for this file on its own. Files of one file set with the same target
move together: if one of them needs a step, such as de-identification, all of them take it. See <a href="processing-rules.html">Rules and targets</a>
for every rule.</div>
<div id="pr-explorer" class="pr-explorer" data-src="assets/data-trajectory.json">
  <p class="muted">Loading the rules…</p>
</div>
<noscript><p>This page needs JavaScript. The same information is on
<a href="processing-rules.html">Rules and targets</a>.</p></noscript>
<script src="assets/data-trajectory.js" defer></script>"""
