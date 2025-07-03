build:
	@docker build -t lattots/simengine -f simengine/Dockerfile .

run: build
	@docker run --rm --name simengine lattots/simengine

lint:
	@uvx ruff check

format:
	@uvx ruff format

