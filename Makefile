.PHONY: lint check enums

lint:
	linkml-lint --config .linkml-lint.yaml header.yaml
	linkml-lint --config .linkml-lint.yaml schema/core.yaml
	linkml-lint --config .linkml-lint.yaml schema/data.yaml
	python3 scripts/check_structure.py schema/data.yaml

# Validate example data file objects, and mutations of them that must fail.
check:
	python3 scripts/check_data_files.py schema/data.yaml

# Regenerate the FHIR resource type and OMOP table enums from HL7 and OHDSI (downloads).
enums:
	python3 scripts/gen_enums.py
