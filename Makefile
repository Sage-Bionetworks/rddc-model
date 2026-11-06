.PHONY: lint fhir-enums

lint:
	linkml-lint --config .linkml-lint.yaml header.yaml
	linkml-lint --config .linkml-lint.yaml schema/core.yaml
	linkml-lint --config .linkml-lint.yaml schema/data.yaml
	python3 scripts/check_structure.py schema/data.yaml

# Regenerate FhirResourceTypeEnum from the FHIR R4 code system (downloads it from hl7.org).
fhir-enums:
	python3 scripts/gen_fhir_enums.py
