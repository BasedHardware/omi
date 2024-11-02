.PHONY: test build clean

test:
	@echo "🧪 Running tests..."
	@dart run build_runner build --delete-conflicting-outputs || { echo "❌ Build runner failed"; exit 1; }
	@if ! "$(CURDIR)/test.sh"; then \
		echo "❌ Tests failed"; \
		echo "Please check the test output above for details"; \
		exit 1; \
	fi
build:
	@echo "🏗️ Building..."
	@dart run build_runner build --delete-conflicting-outputs || { echo "❌ Build failed"; exit 1; }
	@echo "✅ Build completed successfully"
clean:
	@echo "🧹 Cleaning..."
	@command -v flutter >/dev/null 2>&1 || { echo "❌ Flutter not found"; exit 1; }
	@flutter clean
	@rm -rf coverage build 2>/dev/null || true
	@echo "✅ Clean completed successfully"
	@flutter clean
	@rm -rf coverage
	@rm -rf build
