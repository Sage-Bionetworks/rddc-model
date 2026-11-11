# RDDC data model

This repository defines the Rare Disease Data Commons (RDDC) data model in
LinkML, with examples. The schema defines the fields and validation rules; the
documentation site that explains them is on the docs branch. Tools live in
separate repositories and use tagged releases of this model.

A sidecar describes one data deposit. It is a JSON-LD document and a valid
[Croissant 1.1](https://docs.mlcommons.org/croissant/docs/croissant-spec-1.1.html)
dataset, extended with RDDC terms. Every file is a `cr:FileObject` and every
file set a `cr:FileSet`. The RDDC class (`rddc:FhirNdjsonFile`,
`rddc:OmopCdmInstance`, ...) goes in `additionalType` and determines the
required fields. The model uses existing Croissant property names where possible. Its
RDDC fields use camelCase in the `rddc:` namespace.

| Path | What |
| --- | --- |
| `schema/rddc_sidecar.yaml` | LinkML module for the sidecar and the per-source descriptor (schema version 0.1.0) |
| `schema/data.yaml` | LinkML module with the data file classes (`DataFile` and subclasses) and their class annotations: `modality`, `structure`, `fileSetClass`, `biometric`, `identifying` and the sensitivity flags the class fixes |
| `schema/core.yaml` | LinkML module with the shared types, base classes (`FileObject`) and slots, imported by the other two |
| `schema/croissant-1.1-context.json` | Croissant 1.1 JSON-LD context, vendored from mlcroissant 1.1.1 |
| `schema/generated/rddc_sidecar.context.jsonld` | Sidecar JSON-LD context: Croissant's plus the RDDC terms |
| `schema/generated/rddc_sidecar.schema.json` | Closed JSON Schema for the sidecar document |
| `schema/generated/rddc_source_descriptor.schema.json` | Closed JSON Schema for the source descriptor (plain JSON) |
| `examples/` | Example sidecars (deposit, withdrawal, C-CDA document set) and a source descriptor |
| `examples/data_files/valid.json` | One valid data file object per data class, checked by `make check` |
| `scripts/` | Context builder, example and data file checkers, class annotation checker and enum generator |

## Build and check

```bash
pip install linkml
make schema     # JSON-LD context (also refreshed in examples/), then JSON Schemas
make check      # examples and data file objects against the JSON Schemas, plus must-fail mutations
make check CROISSANT_PY=/path/to/python-with-mlcroissant   # also Croissant validation
make lint       # linkml-lint, plus the class annotation check
make enums      # regenerate the FHIR resource type and OMOP table enums from HL7 and OHDSI
```

The `rddc-sidecar` validator checks rules beyond JSON Schema: unique `@id`s
and subject identities, valid references, required subjects, no data files in
withdrawal or restriction batches, and the allowed `conformsTo` values.

## Versioning

The schema follows semantic versioning from 1.0. It is still a draft and may
change before then. The version restarted at 0.1.0 when the model moved to
Croissant. Releases are git tags named `v<major>.<minor>.<patch>`.
Consumers such as [rddc-sidecar](../rddc-sidecar) fetch schema sources by tag,
never from the default branch.

## Consumers

- `rddc-sidecar`: generator and validator for deposit sidecars. Vendors the
  JSON Schema and Pydantic classes generated from `schema/rddc_sidecar.yaml`.
