build-simengine:
	@docker build -t lattots/simengine -f simengine/Dockerfile .

run-simengine: build-simengine
	@docker run --rm --name simengine lattots/simengine

build-optimus:
	@docker build -t lattots/optimus -f optimus/Dockerfile .

run-optimus: build-optimus
	@docker run --rm --name optimus -v "$(PWD)/models:/app/models" lattots/optimus

build-optimus-test:
	@docker build -t lattots/optimus-test -f optimus/test.Dockerfile .

test-optimus: build-optimus-test
	@docker run --rm --name optimus-test -v "$(PWD)/models:/app/models" lattots/optimus-test

lint:
	@uvx ruff check

format:
	@uvx ruff format

