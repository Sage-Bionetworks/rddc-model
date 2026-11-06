# RDDC data model

LinkML data model for the Rare Disease Data Commons (RDDC).

## Layout

| Path | What |
| --- | --- |
| `header.yaml` | Shared LinkML header |
| `schema/core.yaml` | Shared types, base classes (`FileObject`) and slots |
| `schema/data.yaml` | Data file classes (`DataFile` and its subclasses) and their `structure` annotations, imported by the sidecar schema |
| `scripts/check_structure.py` | Checks that every data file class has a valid `structure` annotation |
| `scripts/gen_fhir_enums.py` | Regenerates `FhirResourceTypeEnum` from the FHIR R4 resource-types code system (`make fhir-enums`) |

Run `make lint` to lint the schemas with `.linkml-lint.yaml` and check the `structure` annotations.
