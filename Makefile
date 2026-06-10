TEST_IMAGE = oc-test-image
TEST_CONTAINER = oc-test

.PHONY: build-test test

build-test:
	@docker build -f tests/Dockerfile -t $(TEST_IMAGE) .

test: build-test
	@docker run --rm --name $(TEST_CONTAINER) $(TEST_IMAGE)

