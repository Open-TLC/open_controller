lint:
	@ruff check

UNIT_TEST_IMAGE = oc-unit-test
UNIT_TEST_CONTAINER = oc-unit-test

INTEGRATION_TEST_IMAGE = oc-integration-test
INTEGRATION_TEST_CONTAINER = oc-integration-test

.PHONY: build-test test

build-test:
	@docker build -f tests/unit.Dockerfile -t $(UNIT_TEST_IMAGE) .
	@docker build -f tests/integration.Dockerfile -t $(INTEGRATION_TEST_IMAGE) .

test: build-test
	@docker run --rm --name $(UNIT_TEST_CONTAINER) $(UNIT_TEST_IMAGE)
	@docker run --rm --name $(INTEGRATION_TEST_CONTAINER) $(INTEGRATION_TEST_IMAGE)

