.PHONY: test build clean

test:
	@echo "🧪 Running tests..."
	@dart run build_runner build --delete-conflicting-outputs
	@if ! ./test.sh; then \
		echo "❌ Tests failed"; \
		exit 1; \
	fi

build:
	@echo "🏗️ Building..."
	@dart run build_runner build --delete-conflicting-outputs

clean:
	@echo "🧹 Cleaning..."
	@flutter clean
	@rm -rf coverage
	@rm -rf build
