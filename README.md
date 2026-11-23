# RDDC data model

LinkML data model for the Rare Disease Data Commons (RDDC).

## Standards registry

`schema/standards.yaml` (`rddc-standards`) is a registry of the standards
(ontologies, terminologies, classifications, data models and exchange schemas)
considered for incoming RDDC clinical data. For each standard it records where it
comes from, how its files can be downloaded automatically, how it is licensed and
released, and which data categories and coverage domains it can represent. The
content was first converted from the "RAPID Ontology Exploration" workbook.
Coverage is indicative, not a verified implementation.

| Path                                 | What                                                                                    |
| ------------------------------------ | --------------------------------------------------------------------------------------- |
| `schema/standards.yaml`            | LinkML schema for the registry. The root class is `StandardsCatalog`                  |
| `src/data/standards_registry.yaml` | One `StandardEntry` per standard (21: SNOMED CT, HPO, LOINC, MONDO, ...)              |
| `src/data/data_categories.yaml`    | One `DataCategory` per kind of incoming data (22), with the standards proposed for it |
| `src/data/coverage_domains.yaml`   | The 46 `CoverageDomain`s, each in one of 7 domain groups                              |
| `scripts/merge_data.py`            | Merges the data files into one `StandardsCatalog` document for validation             |

The YAML files under `src/data` are the source of truth. Edit them directly.

### Standard entries

Every entry in `standards_registry.yaml` lists its fields in this order. Leave out
any field that does not apply.

| Group                 | Fields                                                                                                                                          |
| --------------------- | ----------------------------------------------------------------------------------------------------------------------------------------------- |
| Identity              | `id`, `abbreviation`, `name`, `bioregistryPrefix`, `standardType`                                                                     |
| Access methods        | `directDownloadAccess`, `downloadApiAccess`, `webBrowserAccess` (true/false)                                                              |
| Download              | `directDownloadUrls`, `authenticationRequired`, `authenticationType`, `releaseApiUrls`, `downloadApiUrls`, `versionSelectionMethod` |
| Formats and links     | `dataFormats`, `otherUrls` (homepage first, then documentation)                                                                             |
| Licensing and release | `accessRequirements`, `license` (SPDX), `licenseUrl`, `updateFrequency`                                                                 |
| Standard Relevance    | `conformsToUrls`, `alignedCategories`, `coveredDomains`                                                                                   |
| Notes                 | `notes`, `comments`                                                                                                                         |

`standardType` is one of `ONTOLOGY`, `CLINICAL_TERMINOLOGY`, `CLASSIFICATION`,
`NOMENCLATURE`, `UNIT_STANDARD`, `DATABASE`, `COMMON_DATA_MODEL` or
`EXCHANGE_SCHEMA`.

### Download fields

These fields let a downloader fetch a standard's release files without a person.
Using HPO as the example:

| Field                                                          | Purpose                                                                                                                         |
| -------------------------------------------------------------- | ------------------------------------------------------------------------------------------------------------------------------- |
| `directDownloadUrls`                                         | Persistent URLs resolving to the latest HPO ontology files.                                                                     |
| `releaseApiUrls`                                             | Discover available releases, version identifiers, publication dates, and release assets.                                        |
| `downloadApiUrls`                                            | Retrieve a selected GitHub release asset using its dynamically discovered `asset_id`.                                         |
| `authenticationRequired`                                     | Whether downloading needs credentials. Absent means not yet checked.                                                            |
| `authenticationType`                                         | The credential needed: `API_KEY` or `ACCOUNT_LOGIN`.                                                                        |
| `versionSelectionMethod`                                     | How to find the current or a chosen release, such as `RELEASE_API` or `GITHUB_RELEASES`. `NOT_VERIFIED` means no release |
| source is confirmed yet, so downloads should not be automated. |                                                                                                                                 |

### Standard Relevance & Links to Model

- `DataCategory.dataClasses` names the data file classes (`DataFile` subclasses,
  such as `IntakeFormFile`) that carry a category. It is filled only where the
  category and the class match one to one.
- `DataCategory.proposedStandards` refers to standards by their `id`. When you
  rename or remove a standard, update `data_categories.yaml` too: the validator
  does not catch a reference to a missing standard.
- Prefix names and URIs (`SNOMEDCT`, `LOINC`, `ORPHA`, `CHEMBL.COMPOUND`, `sc`, `dct`, ...)
  match `header.yaml`.

### Check

```bash
pip install "linkml==1.11.1"
linkml validate schema/standards.yaml # schema against the LinkML metamodel
linkml-lint --config .linkml-lint.yaml schema/standards.yaml
python scripts/merge_data.py src/data > /tmp/catalog.yaml
linkml validate -s schema/standards.yaml -C StandardsCatalog /tmp/catalog.yaml # the data
```

Note: The data check currently reports six errors: the `downloadApiUrls` of HPO, DOID,
MONDO, MAxO, DUO and DPV contain placeholders (`{asset_id}`, `{tag}`), which are
not valid URIs. These should be updated when version selection is better defined by the group.
