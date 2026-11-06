# RDDC data model

LinkML data model for the Rare Disease Data Commons (RDDC).

## Layout

| Path | What |
| --- | --- |
| `header.yaml` | Shared LinkML header |
| `schema/core.yaml` | Shared types, base classes (`FileObject`) and slots |
| `schema/data.yaml` | Data file classes (`DataFile` and its subclasses), imported by the sidecar schema |

Run `make lint` to lint the schemas with `.linkml-lint.yaml`.
