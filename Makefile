.PHONY: schema lint

SCHEMA=schema/rddc_sidecar.yaml

schema:
	gen-json-schema --closed $(SCHEMA) > schema/generated/rddc_sidecar.schema.json
	gen-json-schema --closed --top-class SourceDescriptor $(SCHEMA) > schema/generated/rddc_source_descriptor.schema.json

lint:
	linkml-lint $(SCHEMA) || true
