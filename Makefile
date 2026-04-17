IMAGE_NAME ?= valkey-hook
IMAGE_TAG ?= latest

.PHONY: all clean test lint format
all clean test lint format:

SHELL := /bin/sh -e

.PHONY: install setup
setup: poetry.lock
	poetry config virtualenvs.in-project true
	poetry install --with dev
	poetry run pre-commit install;

.PHONY: install
install:
	poetry config virtualenvs.in-project true
	poetry install --with dev
	poetry run pre-commit install;

.PHONY: format
format:
ifdef CI
	poetry run pre-commit run --all-files --show-diff-on-failure
else
	# automatically fix the formatting issues and rerun again
	poetry run pre-commit run --all-files || poetry run pre-commit run --all-files
endif

.PHONY: lint
lint: format
	poetry run mypy .apolo

.PHONY: test-unit
test-unit:
	poetry run pytest -vvs --cov=.apolo --cov-report xml:.coverage.unit.xml .apolo/tests/unit

.PHONY: test-integration
test-integration:
	poetry run pytest -vv --cov=.apolo --cov-report xml:.coverage.integration.xml .apolo/tests/integration

.PHONY: test-helm
test-helm:
	helm unittest ./valkey

.PHONY: build-hook-image
build-hook-image:
	DOCKER_BUILDKIT=1 \
	docker build \
		--build-arg APP_IMAGE_TAG=$(IMAGE_TAG) \
		-t $(IMAGE_NAME):latest \
		-f hooks.Dockerfile \
		.;

.PHONY: push-hook-image
push-hook-image:
	docker tag $(IMAGE_NAME):latest ghcr.io/neuro-inc/$(IMAGE_NAME):$(IMAGE_TAG)
	docker push ghcr.io/neuro-inc/$(IMAGE_NAME):$(IMAGE_TAG)

.PHONY: gen-types-schemas
hook-gen-types-schemas:
	app-types dump-types-schema .apolo/src/apolo_apps_valkey ValkeyAppInputs .apolo/src/apolo_apps_valkey/schemas/ValkeyAppInputs.json
	app-types dump-types-schema .apolo/src/apolo_apps_valkey ValkeyAppOutputs .apolo/src/apolo_apps_valkey/schemas/ValkeyAppOutputs.json
