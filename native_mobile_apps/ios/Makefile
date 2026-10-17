.PHONY: generate open build test lint format strings strings-check api api-check check clean migration-e2e

PROJECT := Omi.xcodeproj
SCHEME  := Omi
SIM     ?= Omi Native
DEST    := platform=iOS Simulator,name=$(SIM)
# The Omi repository providing ARB files, the OpenAPI spec and its Swift generator: two levels up
# when this app lives inside it, else the sibling checkout omi-fresh.
OMI_UPSTREAM ?= $(if $(wildcard ../../backend),../..,../omi-fresh)
PACKAGES := OmiCore OmiNetwork OmiPersistence OmiDevice OmiAudio OmiService OmiDesign OmiExtras

generate: ## Produce Omi.xcodeproj from project.yml
	xcodegen generate --quiet

open: generate
	open $(PROJECT)

build: generate ## Debug build for the simulator
	xcodebuild -project $(PROJECT) -scheme $(SCHEME) -configuration Debug -destination '$(DEST)' -derivedDataPath build/DerivedData build | xcbeautify 2>/dev/null || true

test: ## Unit-test every package in isolation
	@for p in $(PACKAGES); do (cd Packages/$$p && swift test) || exit 1; done

L10N := python3 Tools/l10n/arb2xcstrings.py --arb-dir $(OMI_UPSTREAM)/app/lib/l10n --sources App Packages \
	--out Packages/OmiDesign/Sources/OmiDesign/Resources/Localizable.xcstrings

# A native key ships in en + de; the other locales arrive with upstream's translations, so the
# untranslated list is a reminder, not a failure (the ARB keys are still gated: "missing").
strings: ## Regenerate Localizable.xcstrings from the Flutter ARB files + Tools/l10n/native.json
	$(L10N)

strings-check: ## Fail if the committed catalog is stale
	$(L10N) --allow-untranslated
	git diff --exit-code -- Packages/OmiDesign/Sources/OmiDesign/Resources/Localizable.xcstrings

migration-e2e: ## P1 gate (see Tools/dev/migration-e2e.sh); FLUTTER_APP=<Runner.app>
	Tools/dev/migration-e2e.sh $(FLUTTER_APP) build/DerivedData/Build/Products/Debug-iphonesimulator/Omi.app

api: ## Regenerate wire DTOs from the upstream OpenAPI spec plus docs/backend-patches/*.openapi.json
	python3 Tools/api/generate_dtos.py $(OMI_UPSTREAM)

api-check: ## Fail if the generated DTOs are stale
	python3 Tools/api/generate_dtos.py $(OMI_UPSTREAM) --check

lint:
	swiftlint --strict

format:
	swiftformat .

check: generate test lint strings-check api-check ## Full gate: tests, lint, strings, DTOs, Debug + Release build
	xcodebuild -project $(PROJECT) -scheme $(SCHEME) -configuration Debug -destination '$(DEST)' build
	xcodebuild -project $(PROJECT) -scheme $(SCHEME) -configuration Release -destination '$(DEST)' build

clean:
	rm -rf $(PROJECT) build
