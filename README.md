# RDDC data model

LinkML data model for the Rare Disease Data Commons (RDDC).

## Ontology catalog

`schema/ontology.yaml` (`rddc-ontologies`) is a catalog of the ontologies,
terminologies and exchange standards considered for incoming RDDC clinical data.
For each standard it records where it comes from, how it is accessed, licensed and
released, and which data categories and coverage domains it can represent. The
content was converted from the "RAPID Ontology Exploration" workbook. Coverage is
indicative, not a verified implementation.

| Path | What |
| --- | --- |
| `schema/ontology.yaml` | LinkML schema for the catalog. The root class is `OntologyCatalog` |
| `src/data/standards.yaml` | One `StandardEntry` per standard (FHIR, SNOMED CT, HPO, LOINC, MONDO, ...) |
| `src/data/data_categories.yaml` | One `DataCategory` per kind of incoming data, with the standards proposed for it |
| `src/data/coverage_domains.yaml` | The 46 `CoverageDomain`s, each in one of 7 domain groups |
| `scripts/merge_data.py` | Merges the data files into one `OntologyCatalog` document for validation |
| `scripts/xlsx_to_linkml.py` | One-time import from the workbook, with the hand corrections it applied |

The YAML files under `src/data` are the source of truth. Edit them directly. Use
the import script only to reproduce the original conversion.

### Links to the rest of the model

- `StandardEntry.conformsToUrls` gives the versioned URLs that a sidecar file set's
  `conformsTo` uses for a standard, such as `http://hl7.org/fhir/R4`. They match the
  `url` of the processing rules' `Standard`. `StandardEntry` is a separate class:
  it describes a standard, while `Standard` is something a file conforms to.
- `DataCategory.dataClasses` names the data file classes (`DataFile` subclasses,
  such as `IntakeFormFile`) that carry a category. It is filled only where the
  category and the class match one to one.
- Prefix names and URIs (`SNOMEDCT`, `LOINC`, `ORPHA`, `CHEMBL.COMPOUND`, `sc`, `dct`, ...)
  match `header.yaml` and the other modules, so a CURIE expands to the same URI
  everywhere. Keep them in step when you change either file.

### Conventions

These follow the other RDDC modules and are enforced by `.linkml-lint.yaml`:

- Field names are lowerCamelCase, such as `bioregistryPrefix` and `alignedCategories`.
- Record IDs and enum values are UPPER_SNAKE_CASE keys, such as `SNOMEDCT` and `PATIENT_HISTORY`.
- The license is CC0 and the default prefix is `rddc` (`https://w3id.org/rddc/vocab/`).

### Check

```bash
pip install "linkml==1.11.1"
linkml validate schema/ontology.yaml                       # schema against the LinkML metamodel
linkml-lint --config .linkml-lint.yaml schema/ontology.yaml
python scripts/merge_data.py src/data > /tmp/catalog.yaml
linkml validate -s schema/ontology.yaml -C OntologyCatalog /tmp/catalog.yaml   # the data
```

CI runs the first two checks on every push and pull request. It does not yet
validate the data files.
