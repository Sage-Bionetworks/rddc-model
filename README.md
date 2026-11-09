# RDDC data model

LinkML data model for the Rare Disease Data Commons (RDDC).

## Layout

| Path | What |
| --- | --- |
| `header.yaml` | Shared LinkML header |
| `schema/core.yaml` | Shared types, base classes (`FileObject`) and slots |
| `schema/data.yaml` | Data file classes (`DataFile` and its subclasses) and their `structure`, `modality` and `biometric` annotations, imported by the sidecar schema |
| `docs/data_classes.md` | Reference for the data file classes, generated from the schema (`make docs`) |
| `scripts/gen_docs.py` | Generates `docs/data_classes.md`; CI checks it is up to date |
| `scripts/check_data_files.py` | Validates example data file objects, and mutations that must fail, against the generated JSON Schema (`make check`) |
| `scripts/check_structure.py` | Checks the `structure`, `modality` and `biometric` annotations on the data file classes |
| `scripts/gen_enums.py` | Regenerates the versioned FHIR resource type and OMOP table enums, and the rules that tie them to `fhirVersion` and `omopCdmVersion`, from HL7 and OHDSI sources (`make enums`) |

Run `make lint` to lint the schemas with `.linkml-lint.yaml` and check the class annotations, and `make check` to validate the example data file objects.
