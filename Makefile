.PHONY: check

check:
	flake8
	mypy

requirements.txt: pyproject.toml
	CUSTOM_COMPILE_COMMAND='make requirements.txt' pip-compile --output-file=$@ $^

dev-requirements.txt: pyproject.toml
	CUSTOM_COMPILE_COMMAND='make dev-requirements.txt' pip-compile --extra=dev --output-file=$@ $^
