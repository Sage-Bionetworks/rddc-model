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
  match `header.yaml` and the other modules.

