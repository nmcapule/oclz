# Build and run oclz syncing script via docker.
docker-run:
	./scripts/docker_run.sh $(ARGS)

# Build and run oclz syncing script via pypy3.
# Example: make pypy3-run ARGS="--version"
pypy3-run:
	./scripts/pypy3_run.sh $(ARGS)

# Execute pypy if available.
# Example: make pypy3 ARGS="--version"
pypy3:
	./pypy3/bin/pypy $(ARGS)

.PHONY: all pypy3 clean
