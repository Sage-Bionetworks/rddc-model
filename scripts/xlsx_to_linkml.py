"""One-time import of the "RAPID Ontology Exploration" workbook into LinkML data.

Usage:  python scripts/xlsx_to_linkml.py RAPID_Ontology_Exploration.xlsx src/data

After the import, the YAML files under src/data are the source of truth; edit
them directly. Hand-curated corrections (typos, the ICD-10-CM row slip,
category/standard mappings) live in the dictionaries below so the import is
reproducible.
"""
import re
import sys
from pathlib import Path

import openpyxl
import yaml

XLSX, OUT = Path(sys.argv[1]), Path(sys.argv[2])
wb = openpyxl.load_workbook(XLSX, data_only=True)

# ---------------------------------------------------------------- helpers
def key(s):
    s = s.replace("&", " AND ").replace("–", "-")
    return re.sub(r"[^A-Z0-9]+", "_", s.upper()).strip("_")

def clean(v):
    if v is None:
        return None
    if isinstance(v, str):
        v = re.sub(r"[ \t]+", " ", v).strip()
        return v or None
    return v

def clean_url(u):
    if not u:
        return None
    u = re.sub(r"[?&]utm_source=chatgpt\.com", "", u.strip())
    return u

def link(ws, coord):
    c = ws[coord]
    return clean_url(c.hyperlink.target) if c.hyperlink else None

def comment(ws, coord):
    c = ws[coord]
    if not c.comment:
        return None
    t = c.comment.text.split("Comment:", 1)[-1]
    t = t.split("\nReply:")[0]
    return clean(t.replace("\n", " "))

def prune(d):
    """Drop empty values so the YAML stays readable."""
    if isinstance(d, dict):
        return {k: prune(v) for k, v in d.items() if v not in (None, [], "", {})}
    if isinstance(d, list):
        return [prune(x) for x in d]
    return d

def dump(name, payload):
    OUT.mkdir(parents=True, exist_ok=True)
    with open(OUT / name, "w") as f:
        yaml.safe_dump(prune(payload), f, sort_keys=False, allow_unicode=True, width=100)

def split_list(s, sep=r"[;,\n]"):
    return [x.strip() for x in re.split(sep, s or "") if x.strip()]

# ---------------------------------------------------------------- standards
STD_IDS = {
    "HL7 FHIR": "FHIR", "SNOMED CT": "SNOMEDCT", "HPO": "HPO", "LOINC": "LOINC",
    "GA4GH Phenopackets": "PHENOPACKETS", "ICD-10-CM": "ICD10CM", "DOID / DO": "DOID",
    "MONDO": "MONDO", "IDO": "IDO", "MAxO": "MAXO", "ORDO": "ORDO", "PJO": "PJO",
    "RxNorm": "RXNORM", "DrugBank": "DRUGBANK", "ChEMBL": "CHEMBL", "SO": "SO",
    "HGVS": "HGVS", "UCUM": "UCUM",
}
def std_id(label):
    return STD_IDS[label.replace("*", "").strip()]

TYPE_MAP = {
    "Ontology": "ONTOLOGY", "Ontology (scope to verify)": "ONTOLOGY",
    "Clinical terminology": "CLINICAL_TERMINOLOGY",
    "Observation terminology": "OBSERVATION_TERMINOLOGY",
    "Drug terminology": "DRUG_TERMINOLOGY", "Classification": "CLASSIFICATION",
    "Nomenclature": "NOMENCLATURE", "Unit standard": "UNIT_STANDARD",
    "Database": "DATABASE", "Data exchange standard": "DATA_EXCHANGE_STANDARD",
    "Case exchange standard": "CASE_EXCHANGE_STANDARD",
}

FIXES = {  # typo -> correction, applied to Ontology Sources text cells
    "downlaods": "downloads", "Dowload": "Download", "JASON": "JSON", "OBOl": "OBO",
    "PostgresSQL": "PostgreSQL", "Licence": "License", "Bianual": "Biannual",
    "Bi-anually": "Biannual", "Bi-annually": "Biannual",
}
def fix(s):
    if not s:
        return s
    for a, b in FIXES.items():
        s = s.replace(a, b)
    return s

FORMATS = {  # cleaned Data Formats per standard
    "SNOMEDCT": ["RF2 (tab-delimited text, UTF-8)"], "PHENOPACKETS": ["Protobuf", "JSON"],
    "RXNORM": ["RRF (UTF-8)"],
}
# Licenses stated unambiguously by the linked license page or the cell text.
SPDX = {
    "https://creativecommons.org/licenses/by/4.0/": "CC-BY-4.0",
    "https://creativecommons.org/licenses/by/4.0": "CC-BY-4.0",
    "https://creativecommons.org/licenses/by/3.0/": "CC-BY-3.0",
    "http://creativecommons.org/licenses/by-nc/4.0/legalcode": "CC-BY-NC-4.0",
}
LICENSE_TEXT_SPDX = {"BSD 3-Clause License": "BSD-3-Clause"}

def parse_version(v):
    """'2.83 (2026-08-29)' -> ('2.83', '2026-08-29'); 'v2026-09-01' -> ('v2026-09-01', '2026-09-01')."""
    if not v:
        return None, None
    v = clean(str(v))
    m = re.search(r"(\d{4})-?(\d{2})-?(\d{1,2})\)?$", v.replace("Edition ", "Edition-"))
    date = None
    if m:
        date = f"{m.group(1)}-{m.group(2)}-{int(m.group(3)):02d}"
    label = re.sub(r"\s*\((\d{4}-\d{2}(-\d{1,2})?)\)$", "", v)
    return label, date

standards = {}
notes_log = []  # issues to record in docs/conversion-notes.md

# Ontology Coverage sheet: names, types, 46 domains, 7 group flags
cov = wb["Ontology Coverage"]
crow = [list(r) for r in cov.iter_rows(values_only=True) if any(v is not None for v in r)]
split = [i for i, r in enumerate(crow) if r[0] == "Abbreviation"][1]
domain_titles = crow[0][4:50]
group_titles = crow[split][2:9]
GROUP_IDS = ["PATIENT_AND_CONTEXT", "PHENOTYPE_AND_DISEASE", "CLINICAL_ACTIVITIES",
             "OBSERVATIONS_AND_SPECIMENS", "GENOMIC_AND_MOLECULAR",
             "DRUGS_AND_THERAPEUTICS", "INFORMATION_AND_INTEROPERABILITY"]
GROUP_SIZES = [8, 9, 6, 8, 5, 5, 5]  # domain columns are laid out group by group
dom_group = []
for gid, n in zip(GROUP_IDS, GROUP_SIZES):
    dom_group += [gid] * n
assert len(dom_group) == len(domain_titles) == 46
domains = [{"id": key(t), "name": t, "group": g} for t, g in zip(domain_titles, dom_group)]
dom_ids = [d["id"] for d in domains]

for r in crow[1:split]:
    sid = std_id(r[0])
    covered = [d for d, v in zip(dom_ids, r[4:50]) if v == "✓"]
    assert len(covered) == r[3], (sid, "coverage count")
    standards[sid] = {
        "id": sid, "abbreviation": r[0], "name": r[1],
        "standardType": TYPE_MAP[r[2]],
        "scopeToVerify": True if "scope to verify" in r[2] else None,
        "coveredDomains": covered,
    }
# check the 7-group summary table is reproduced by the domain->group mapping
for r in crow[split + 1:]:
    stated = {g for g, v in zip(GROUP_IDS, r[2:9]) if v is True}
    derived = {dom_group[dom_ids.index(d)] for d in standards[std_id(r[0])]["coveredDomains"]}
    assert stated == derived, (r[0], stated ^ derived)

# Ontology Allignments sheet: 21 data-category columns
al = wb["Ontology Allignments"]
arow = [list(r) for r in al.iter_rows(values_only=True)]
cat_titles = arow[0][3:24]
CAT_IDS = [key(t) for t in cat_titles]
for r in arow[1:]:
    if not r[0]:
        continue
    sid = std_id(r[0])
    aligned = [c for c, v in zip(CAT_IDS, r[3:24]) if v is True]
    assert len(aligned) == r[2], (sid, "alignment count")
    standards[sid]["alignedCategories"] = aligned
    if "**" in r[0]:
        standards[sid].setdefault("notes", []).append(
            "Marked ** in the workbook; the footnote it refers to is not in the file.")

# Ontology Sources sheet
src = wb["Ontology Sources"]
for i, r in enumerate(src.iter_rows(min_row=2, values_only=True), start=2):
    if not r[0]:
        continue
    sid = std_id(r[0])
    s = standards[sid]
    s["homepage"] = clean_url(link(src, f"C{i}") or r[2])
    s["accessMethods"] = [fix(x) for x in split_list(r[3], r"[;\n]")]
    s["accessUrls"] = [u for u in [link(src, f"D{i}")] if u]
    s["dataFormats"] = FORMATS.get(sid) or [fix(x) for x in split_list(r[4], r"[;,]")]
    s["accessRequirements"] = fix(clean(r[5]))
    s["licenseUrl"] = link(src, f"F{i}")
    s["license"] = SPDX.get(s["licenseUrl"]) or LICENSE_TEXT_SPDX.get(clean(r[5]))
    s["version"], s["versionDate"] = parse_version(r[6])
    s["updateFrequency"] = fix(clean(r[7]))
    if clean(r[8]):
        s.setdefault("notes", []).append(clean(r[8]))
    c = comment(src, f"A{i}")
    if c:
        s.setdefault("comments", []).append(c)
    if clean(r[1]) and clean(r[1]) != s["name"]:
        s.setdefault("notes", []).append(f'Named "{clean(r[1])}" on the Ontology Sources sheet.')

# --- hand corrections --------------------------------------------------------
# ICD-10-CM's version and frequency were entered on the Phenopackets row.
ph, icd = standards["PHENOPACKETS"], standards["ICD10CM"]
icd["version"], icd["versionDate"] = ph.pop("version"), ph.pop("versionDate")
icd["updateFrequency"] = ph.pop("updateFrequency")
icd.setdefault("notes", []).append(
    "Version and update frequency were entered on the GA4GH Phenopackets row in the "
    "workbook and moved here during conversion.")
notes_log.append("Moved 'ICD-10-CM FY27 (2026-10-1)' and '~Annual' from the GA4GH "
                 "Phenopackets row to ICD-10-CM (row slip in Ontology Sources).")

ido = standards["IDO"]
if ido.get("version") == "OOD":
    ido["version"] = None
    ido.setdefault("notes", []).append(
        'Last Version Verified was recorded as "OOD" (meaning unclear, possibly "out of date").')
ucum = standards["UCUM"]
if ucum.get("accessRequirements") == "???":
    ucum["accessRequirements"] = None
    ucum.setdefault("notes", []).append('Access Requirements recorded as "???" in the workbook.')
chembl = standards["CHEMBL"]
chembl["version"], chembl["versionDate"] = "ChEMBL 36", None
chembl.setdefault("notes", []).append("Verified release dated 2025-07 (no day given).")

# Text says "Public Domain" but the linked license page says otherwise.
for sid, s in standards.items():
    if s.get("accessRequirements") == "Public Domain" and s.get("license"):
        s.setdefault("notes", []).append(
            f'Workbook says "Public Domain" but the linked license is {s["license"]}.')
        notes_log.append(f"{s['abbreviation']}: 'Public Domain' conflicts with linked license {s['license']}.")

# Standards named only on the Incoming Data sheet.
EXTRA = {
    "OMOP": ("OMOP", "Observational Medical Outcomes Partnership Common Data Model", "COMMON_DATA_MODEL"),
    "DUO": ("DUO", "Data Use Ontology", "ONTOLOGY"),
    "ODRL": ("ODRL", "Open Digital Rights Language", "VOCABULARY"),
    "DPV": ("DPV", "Data Privacy Vocabulary", "VOCABULARY"),
}
for sid, (ab, nm, ty) in EXTRA.items():
    standards[sid] = {"id": sid, "abbreviation": ab, "name": nm, "standardType": ty,
                      "notes": ["Named only on the Incoming Data sheet; not yet assessed "
                                "on the coverage or sources sheets."]}

# Canonical Bioregistry prefixes, each checked against https://bioregistry.io/<prefix>.
BIOREGISTRY = {
    "SNOMEDCT": "snomedct", "HPO": "hp", "LOINC": "loinc", "ICD10CM": "icd10cm",
    "DOID": "doid", "MONDO": "mondo", "IDO": "ido", "MAXO": "maxo",
    "ORDO": "orphanet.ordo", "RXNORM": "rxnorm", "DRUGBANK": "drugbank",
    "CHEMBL": "chembl", "SO": "so", "HGVS": "hgvs", "UCUM": "ucum",
    "OMOP": "omop", "DUO": "duo", "ODRL": "odrl", "DPV": "dpvocab",
}
NO_BIOREGISTRY = {  # no matching Bioregistry entry found
    "FHIR": "No Bioregistry entry for HL7 FHIR itself (only related entries such as "
            "hl7.v2codesystem, hl7.v3codesystem and fhir.implementation).",
    "PHENOPACKETS": "No Bioregistry entry for the GA4GH Phenopacket Schema.",
    "PJO": "No Bioregistry entry. PJO is described in arXiv:2506.18772 (2025).",
}
for sid, s in standards.items():
    s["bioregistryPrefix"] = BIOREGISTRY.get(sid)
    if sid in NO_BIOREGISTRY:
        s.setdefault("notes", []).append(NO_BIOREGISTRY[sid])
standards["CHEMBL"].setdefault("notes", []).append(
    "Bioregistry prefix chembl is the database as a whole; compound identifiers "
    "(CHEMBL25 etc.) use chembl.compound.")
standards["DPV"].setdefault("notes", []).append(
    "Bioregistry prefix is dpvocab; the prefix dpv belongs to an unrelated resource "
    "(Description of Plant Viruses).")

# Versioned URLs the sidecar's conformsTo uses (the url of the processing rules' Standard).
CONFORMS_TO = {"FHIR": ["http://hl7.org/fhir/R4"],
               "OMOP": ["https://ohdsi.github.io/CommonDataModel/cdm54.html"]}
for sid, urls in CONFORMS_TO.items():
    standards[sid]["conformsToUrls"] = urls

ORDER = ["FHIR", "SNOMEDCT", "HPO", "LOINC", "PHENOPACKETS", "ICD10CM", "DOID", "MONDO",
         "IDO", "MAXO", "ORDO", "PJO", "RXNORM", "DRUGBANK", "CHEMBL", "SO", "HGVS", "UCUM",
         "OMOP", "DUO", "ODRL", "DPV"]
FIELD_ORDER = ["id", "abbreviation", "name", "bioregistryPrefix", "standardType", "scopeToVerify", "homepage",
               "accessMethods", "accessUrls", "dataFormats", "accessRequirements",
               "license", "licenseUrl", "version", "versionDate", "updateFrequency",
               "conformsToUrls", "alignedCategories", "coveredDomains", "notes", "comments"]
dump("standards.yaml", {"standards": [
    {f: standards[s].get(f) for f in FIELD_ORDER} for s in ORDER]})
dump("coverage_domains.yaml", {"coverageDomains": domains})

# ---------------------------------------------------------------- data categories
inc = wb["Incoming Data"]
ROW_TO_CAT = {  # Incoming Data row label -> alignment column id
    "Patient Profle": "PATIENT_PROFILE", "Anamnesis/Patient History": "PATIENT_HISTORY",
    "Assessments": "ASSESSMENTS", "EHR Structured Data and Unstructured Data": "EHR_DATA",
    "Allergies": "ALLERGIES", "Social habits / Risk Factors": "SOCIAL_HABITS_RISK_FACTORS",
    "Family History": "FAMILY_HISTORY", "Genetic Testing/Molecular Pathology": "GENETIC_TESTING",
    "ID ICD-codes/ SNOMED": "ICD_SNOMED_CODES", "Intake Forms": "INTAKE_FORMS",
    "List of medications": "MEDICATIONS", "Patient Reported Outcomes": "PATIENT_REPORTED_OUTCOMES",
    "Patient-reported data. Structured": "STRUCTURED_PATIENT_REPORTS",
    "Phenotypic Data (adhering to GA4GH Ontologies)": "PHENOTYPIC_DATA",
    "Referral Notes": "REFERRAL_NOTES", "Specialist Findings": "SPECIALIST_FINDINGS",
    "Symptoms": "SYMPTOMS", "Visit Notes": "VISIT_NOTES",
    "Vitals and other measurements": "VITALS_MEASUREMENTS", "Facial Images": "FACIAL_IMAGES",
    "Preliminary Differential Diagnosis Support Report": "DIFFERENTIAL_DIAGNOSIS_REPORT",
    "Data Use Restrictions": "DATA_USE_RESTRICTIONS",
}
PROPOSED = {  # hand-parsed from the Ontologies column
    "PATIENT_HISTORY": ["HPO", "SNOMEDCT", "DOID", "LOINC"],
    "ASSESSMENTS": ["SNOMEDCT", "MAXO"],
    "EHR_DATA": ["FHIR", "OMOP"],
    "ALLERGIES": ["SNOMEDCT", "HPO", "RXNORM"],
    "SOCIAL_HABITS_RISK_FACTORS": ["PJO"],
    "FAMILY_HISTORY": ["DOID", "IDO", "MONDO"],
    "ICD_SNOMED_CODES": ["SNOMEDCT"],
    "INTAKE_FORMS": ["PJO"],
    "MEDICATIONS": ["RXNORM", "DRUGBANK", "CHEMBL"],
    "PHENOTYPIC_DATA": ["PHENOPACKETS"],
    "SYMPTOMS": ["HPO"],
    "VITALS_MEASUREMENTS": ["LOINC"],
    "DIFFERENTIAL_DIAGNOSIS_REPORT": ["SNOMEDCT", "ICD10CM", "ORDO"],
    "DATA_USE_RESTRICTIONS": ["DUO", "ODRL", "DPV"],
}
UNCERTAIN = {"SYMPTOMS": ["PHENOPACKETS"]}  # written "GA4GH?"
# Data file classes in data.yaml that match a category one to one.
DATA_CLASSES = {
    "INTAKE_FORMS": ["IntakeFormFile"], "GENETIC_TESTING": ["GeneticTestResultFile"],
    "DIFFERENTIAL_DIAGNOSIS_REPORT": ["DifferentialDiagnosisFile"],
    "FACIAL_IMAGES": ["FacialImagingFile"],
}
cat_title = dict(zip(CAT_IDS, cat_titles))
cat_title["DATA_USE_RESTRICTIONS"] = "Data Use Restrictions"
YN = {"Y": True, "N": False}

categories = []
for i, r in enumerate(inc.iter_rows(min_row=2, values_only=True), start=2):
    label = clean(r[0])
    if not label:
        continue
    cid = ROW_TO_CAT[label]
    c = {
        "id": cid, "name": cat_title[cid], "sourceLabel": label,
        "details": clean(r[1]), "categorical": YN.get(clean(r[2])),
        "source": clean(r[3]), "structure": clean(r[4]),
        "dataClasses": DATA_CLASSES.get(cid),
        "proposedStandards": PROPOSED.get(cid),
        "proposedStandardsUncertain": UNCERTAIN.get(cid),
        "proposedStandardsText": clean(r[5]),
        "seeAlso": [u for u in [link(inc, f"F{i}")] if u],
        "comments": [x for x in [comment(inc, f"A{i}"), comment(inc, f"F{i}")] if x],
    }
    if cid == "DATA_USE_RESTRICTIONS":
        c["notes"] = ["Not a column of the alignment matrix."]
    categories.append(c)
assert {c["id"] for c in categories} >= set(CAT_IDS)
header_comment = comment(inc, "D1")  # "Add in TA1 v TA2" on the Source? column
dump("data_categories.yaml", {
    "notes": [f"Open item from the Incoming Data sheet (comment on the Source? column): {header_comment}"],
    "dataCategories": categories})

print("standards", len(standards), "| domains", len(domains), "| categories", len(categories))
for n in notes_log:
    print("NOTE:", n)
