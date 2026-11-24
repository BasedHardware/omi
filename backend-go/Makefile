# backend-go: one command per job. `make check` is what CI runs and what you run before pushing.
GO ?= go
GOLANGCI_VERSION := v2.15.0
# Pinned and run through the module cache, so every machine lints with the same binary.
GOLANGCI ?= $(GO) run github.com/golangci/golangci-lint/v2/cmd/golangci-lint@$(GOLANGCI_VERSION)
# The conformance kit (stub server, vectors, black-box suites). Optional.
KIT ?=
IMAGE ?= omi-workerd:local
PLATFORM ?= linux/amd64

.PHONY: build image fmt vet lint arch test quick check test-public test-transcript-parity
build:
	$(GO) build -o bin/jobd ./cmd/jobd

image:
	docker build --platform "$(PLATFORM)" --tag "$(IMAGE)" .

fmt:
	$(GOLANGCI) fmt ./...

vet:
	$(GO) vet ./...

lint:
	$(GOLANGCI) run ./...

# Structural rules a linter cannot express: see tools/archcheck.
arch:
	$(GO) run ./tools/archcheck .

# Every test, with the race detector, against Postgres 16 and the Firestore emulator. Each
# script uses the server named in its variable (TEST_DATABASE_URL, FIRESTORE_EMULATOR_HOST)
# when set and otherwise starts a private one for the run. A run with no Postgres fails: it is
# never reported as a pass with the database tests skipped. Firestore tests skip with a notice
# on a machine without the emulator; CI always runs them.
test:
	./scripts/with-postgres.sh ./scripts/with-firestore.sh $(GO) test -race -count=1 ./...

# The tests that need no database, for a fast loop while editing pure code. Not a
# substitute for `make check`.
quick:
	$(GO) test -count=1 ./...
	@echo "quick: database tests were skipped. Run 'make check' before pushing."

check: vet lint arch test

test-public: build
	@test -n "$(KIT)" || { echo "set KIT=/path/to/kit" >&2; exit 2; }
	KIT="$(KIT)" GO="$(GO)" ./scripts/conformance.sh public

# PL-745: the serving Python callback and the Go worker both retain unreadable ciphertext.
test-transcript-parity:
	cd ../backend && bash test.sh tests/unit/test_enrichment_route.py::test_wrong_key_transcript_keeps_ciphertext_and_retries
	TEST_FIRESTORE_REQUIRED=1 ./scripts/with-postgres.sh ./scripts/with-firestore.sh $(GO) test -race -count=1 ./cmd/workerd
