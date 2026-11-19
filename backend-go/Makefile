# backend-go: one command per job. `make check` is what CI runs and what you run before pushing.
GO ?= go
GOLANGCI_VERSION := v2.15.0
# Pinned and run through the module cache, so every machine lints with the same binary.
GOLANGCI ?= $(GO) run github.com/golangci/golangci-lint/v2/cmd/golangci-lint@$(GOLANGCI_VERSION)
# Set to a Postgres 16 URL to run the queue's integration tests; without it they skip.
QUEUE_TEST_DATABASE_URL ?=
# The conformance kit (stub server, vectors, black-box suites). Optional.
KIT ?=

.PHONY: build fmt vet lint arch test check test-public
build:
	$(GO) build -o bin/jobd ./cmd/jobd

fmt:
	$(GOLANGCI) fmt ./...

vet:
	$(GO) vet ./...

lint:
	$(GOLANGCI) run ./...

# Structural rules a linter cannot express: see tools/archcheck.
arch:
	$(GO) run ./tools/archcheck .

test:
	QUEUE_TEST_DATABASE_URL="$(QUEUE_TEST_DATABASE_URL)" $(GO) test -race -count=1 ./...

check: vet lint arch test

test-public: build
	@test -n "$(KIT)" || { echo "set KIT=/path/to/kit" >&2; exit 2; }
	KIT="$(KIT)" GO="$(GO)" ./scripts/conformance.sh public
