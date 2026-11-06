.PHONY: schema context check lint enums docs

SCHEMA=schema/rddc_sidecar.yaml
# Interpreter with mlcroissant installed, for the Croissant half of `make check`.
CROISSANT_PY?=python3

schema: context
	gen-json-schema --closed $(SCHEMA) > schema/generated/rddc_sidecar.schema.json
	gen-json-schema --closed --top-class SourceDescriptor $(SCHEMA) > schema/generated/rddc_source_descriptor.schema.json

context:
	python3 scripts/build_context.py $(SCHEMA) schema/croissant-1.1-context.json \
		schema/generated/rddc_sidecar.context.jsonld examples/*.json

# Example sidecars and data file objects, plus mutations of them that must fail.
check:
	python3 scripts/check_data_files.py schema/data.yaml
	$(CROISSANT_PY) scripts/check_examples.py
	python3 scripts/check_version.py

lint:
	linkml-lint --config .linkml-lint.yaml header.yaml
	linkml-lint --config .linkml-lint.yaml schema/core.yaml
	linkml-lint --config .linkml-lint.yaml schema/data.yaml
	linkml-lint --config .linkml-lint.yaml $(SCHEMA)
	python3 scripts/check_structure.py schema/data.yaml

# Regenerate the FHIR resource type and OMOP table enums from HL7 and OHDSI (downloads).
enums:
	python3 scripts/gen_enums.py
	python3 scripts/gen_docs.py

# Regenerate docs/data_classes.md from the schema; CI fails if it is out of date.
docs:
	python3 scripts/gen_docs.py
