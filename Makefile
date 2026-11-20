.PHONY: schema context check lint enums site

SCHEMA=schema/rddc_sidecar.yaml
# Interpreter with mlcroissant installed, for the Croissant half of `make check`.
CROISSANT_PY?=python3

# The data class schemas (JSON Schema and SHACL shapes) are published as on the
# data-classes branch; the sidecar's own JSON Schemas and context follow.
schema: context
	gen-json-schema --closed schema/data.yaml > schema/generated/data.schema.json
	gen-shacl schema/data.yaml > schema/generated/data.shacl.ttl
	gen-json-schema --closed $(SCHEMA) > schema/generated/rddc_sidecar.schema.json
	gen-json-schema --closed --top-class SourceDescriptor $(SCHEMA) > schema/generated/rddc_source_descriptor.schema.json

context:
	python3 scripts/build_context.py $(SCHEMA) schema/croissant-1.1-context.json \
		schema/generated/rddc_sidecar.context.jsonld examples/*.json

# Example sidecars and data file objects, plus mutations of them that must fail.
check:
	python3 scripts/check_data_files.py schema/data.yaml
	$(CROISSANT_PY) scripts/check_examples.py

lint:
	linkml-lint --config .linkml-lint.yaml header.yaml
	linkml-lint --config .linkml-lint.yaml schema/core.yaml
	linkml-lint --config .linkml-lint.yaml schema/data.yaml
	linkml-lint --config .linkml-lint.yaml $(SCHEMA)
	python3 scripts/check_structure.py schema/data.yaml

# Documentation site into site/dist, including the data class pages; checks the
# recipes and data file examples first.
site:
	python3 scripts/build_site.py

# Regenerate the FHIR resource type and OMOP table enums from HL7 and OHDSI (downloads).
enums:
	python3 scripts/gen_enums.py
