# RDDC data model

LinkML data model for the Rare Disease Data Commons (RDDC), with the
requirements documents the schemas implement. This repository is the
governed source of truth; tooling that consumes the schemas lives in
separate repositories and pins a tagged release of this one.

| Path | What |
| --- | --- |
| `Metadata_Sidecar_Requirements.md` | Metadata sidecar requirements, v0.2 (draft for TA1–TA3 review) |
| `docs/requirements_review.md` | Review of the v0.1 draft against the RDDC Infrastructure Plan |
| `schema/rddc_sidecar.yaml` | LinkML module for the metadata sidecar and the per-source descriptor (schema version 0.2.0) |
| `schema/generated/rddc_sidecar.schema.json` | Closed JSON Schema for the sidecar document, generated from the LinkML source |
| `schema/generated/rddc_source_descriptor.schema.json` | Closed JSON Schema for the source descriptor the ACT issues at onboarding (FR-28) |

## Regenerating artifacts

```bash
pip install linkml
make schema     # gen-json-schema --closed -> schema/generated/
make lint       # linkml-lint
```

## Versioning

Schema modules follow semantic versioning (see the requirements, "Versioning,
provenance and lineage"). Releases are git tags named `v<major>.<minor>.<patch>`;
consumers such as [rddc-sidecar](../rddc-sidecar) fetch schema sources by tag,
never from the default branch.

## Consumers

- `rddc-sidecar`: generator and validator for deposit sidecars. Vendors the
  JSON Schema and Pydantic classes generated from `schema/rddc_sidecar.yaml`.
