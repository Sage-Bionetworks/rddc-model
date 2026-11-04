.PHONY: schema context check lint site

SCHEMA=schema/rddc_sidecar.yaml
# Interpreter with mlcroissant installed, for the Croissant half of `make check`.
CROISSANT_PY?=python3

schema: context
	gen-json-schema --closed $(SCHEMA) > schema/generated/rddc_sidecar.schema.json
	gen-json-schema --closed --top-class SourceDescriptor $(SCHEMA) > schema/generated/rddc_source_descriptor.schema.json

context:
	python3 scripts/build_context.py $(SCHEMA) schema/croissant-1.1-context.json \
		schema/generated/rddc_sidecar.context.jsonld examples/*.json

check:
	$(CROISSANT_PY) scripts/check_examples.py

lint:
	linkml-lint $(SCHEMA) || true

site:
	python3 scripts/build_site.py
