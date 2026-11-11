# RDDC data model

This repository defines the Rare Disease Data Commons (RDDC) data model in
LinkML. It also holds the requirements, examples and documentation. The schema
defines the fields and validation rules; the requirements explain why they
exist. Tools live in separate repositories and use tagged releases of this model.

A sidecar describes one data deposit. It is a JSON-LD document and a valid
[Croissant 1.1](https://docs.mlcommons.org/croissant/docs/croissant-spec-1.1.html)
dataset, extended with RDDC terms. Every file is a `cr:FileObject` and every
file set a `cr:FileSet`. The RDDC class (`rddc:FhirNdjsonFile`,
`rddc:OmopCdmInstance`, ...) goes in `additionalType` and determines the
required fields. The model uses existing Croissant property names where possible. Its
RDDC fields use camelCase in the `rddc:` namespace.

| Path | What |
| --- | --- |
| `docs/sidecar_requirements.md` | Metadata sidecar requirements, v0.2 (draft for TA1–TA3 review) |
| `schema/rddc_sidecar.yaml` | LinkML module for the sidecar and the per-source descriptor (schema version 0.1.0) |
| `schema/data.yaml` | LinkML module with the file classes: `FileObject`, with the fields every file has (`contentUrl`, `contentSize`, `encodingFormat`, `md5`), and the data file classes (`DataFile` and subclasses) with their class annotations: `modality`, `structure`, `fileSetClass`, `biometric`, `identifying` and the sensitivity flags the class fixes |
| `schema/core.yaml` | LinkML module with the shared identifier types, small supporting classes (references, external identifiers, extensions, sensitivity flags, value origins) and their slots, imported by the other two |
| `schema/croissant-1.1-context.json` | Croissant 1.1 JSON-LD context, vendored from mlcroissant 1.1.1 |
| `schema/generated/rddc_sidecar.context.jsonld` | Sidecar JSON-LD context: Croissant's plus the RDDC terms |
| `schema/generated/rddc_sidecar.schema.json` | Closed JSON Schema for the sidecar document |
| `schema/generated/rddc_source_descriptor.schema.json` | Closed JSON Schema for the source descriptor (plain JSON) |
| `examples/` | Example sidecars (deposit, withdrawal, C-CDA document set) and a source descriptor |
| `examples/data_files/valid.json` | One valid data file object per data class, checked by `make check` and shown on the site |
| `site/` | Documentation site sources: pages, recipe sidecars, template and assets. The data classes are documented here, generated from the schema |
| `site/slides.html` | Standalone four-slide presentation on Croissant and the RDDC sidecar |
| `scripts/` | Context builder, example and data file checkers, class annotation checker, version checker, enum generator and site builder |

## Build and check

```bash
pip install linkml
make schema     # JSON-LD context (also refreshed in examples/), then JSON Schemas
make check      # examples and data file objects against the JSON Schemas, plus must-fail mutations
make check CROISSANT_PY=/path/to/python-with-mlcroissant   # also Croissant validation
make lint       # linkml-lint, plus the class annotation check
make enums      # regenerate the FHIR resource type and OMOP table enums from HL7 and OHDSI
make site       # documentation and slides into site/dist (checks the recipes and data file examples first; CI builds it too)
```

The presentation is built at `site/dist/slides.html` and linked from the docs.
It includes its styles and script, so the downloaded HTML works offline.
Arrow keys navigate, F toggles fullscreen, and Print / PDF prints all four slides.

The `rddc-sidecar` validator checks rules beyond JSON Schema: unique `@id`s
and subject identities, valid references, required subjects, no data files in
withdrawal or restriction batches, and the allowed `conformsTo` values.

CI publishes the generated JSON Schemas, SHACL shapes and JSON-LD context as a
workflow artifact on every run and attaches them to the GitHub release of a
`v<major>.<minor>.<patch>` tag.

## Versioning

The schema follows semantic versioning from 1.0. It is still a draft and may
change before then. The version restarted at 0.1.0 when the model moved to
Croissant. Releases are git tags named `v<major>.<minor>.<patch>`; CI fails a
tag that does not match the modules' `version`, and `make check` fails if the
modules or the examples disagree on it.
Consumers such as [rddc-sidecar](../rddc-sidecar) fetch schema sources by tag,
never from the default branch.

## Consumers

- `rddc-sidecar`: generator and validator for deposit sidecars. Vendors the
  JSON Schema and Pydantic classes generated from `schema/rddc_sidecar.yaml`.

## Funding

This research was, in part, funded by the Advanced Research Projects Agency for Health (ARPA-H). The views and conclusions contained in this document are those of the authors and should not be interpreted as representing the official policies, either expressed or implied, of the United States Government.
