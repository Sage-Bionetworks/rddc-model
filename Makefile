.PHONY: lint

lint:
	linkml-lint --config .linkml-lint.yaml header.yaml
	linkml-lint --config .linkml-lint.yaml schema/core.yaml
	linkml-lint --config .linkml-lint.yaml schema/data.yaml
