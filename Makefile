.PHONY: lint check enums schema

lint:
	linkml-lint --config .linkml-lint.yaml header.yaml
	linkml-lint --config .linkml-lint.yaml schema/core.yaml
	linkml-lint --config .linkml-lint.yaml schema/data.yaml
	python3 scripts/check_structure.py schema/data.yaml

# Publish the data class schemas: a closed JSON Schema and SHACL shapes (RDF, Turtle),
# generated from schema/data.yaml into schema/generated/. The JSON Schema is committed
# and CI checks it is current; the SHACL file is regenerated on every build, since
# the generator's output is not byte-for-byte stable.
schema:
	mkdir -p schema/generated
	gen-json-schema --closed schema/data.yaml > schema/generated/data.schema.json
	gen-shacl schema/data.yaml > schema/generated/data.shacl.ttl

# Validate example data file objects, and mutations of them that must fail.
check:
	python3 scripts/check_data_files.py schema/data.yaml

# Regenerate the FHIR resource type and OMOP table enums from HL7 and OHDSI (downloads).
enums:
	python3 scripts/gen_enums.py
