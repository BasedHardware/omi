# Variables
PYTHON = python3
VENV = .venv
PIP = $(VENV)/bin/pip
PYTHON_VENV = $(VENV)/bin/python
PYTEST = $(VENV)/bin/pytest
UVICORN = $(VENV)/bin/uvicorn
FLAKE8 = $(VENV)/bin/flake8
BLACK = $(VENV)/bin/black
BANDIT = $(VENV)/bin/bandit
SAFETY = $(VENV)/bin/safety
MYPY = $(VENV)/bin/mypy

# Environment Setup
.PHONY: setup
setup: $(VENV)/bin/activate install-deps install-test-deps

$(VENV)/bin/activate:
	$(PYTHON) -m venv $(VENV)
	$(PIP) install --upgrade pip

.PHONY: install-deps
install-deps:
	$(PIP) install -r requirements.txt

.PHONY: install-test-deps
install-test-deps:
	$(PIP) install pytest pytest-cov pytest-asyncio httpx

# Development
.PHONY: run
run:
	ENABLE_SWAGGER=true ENABLE_RATE_LIMIT=true $(UVICORN) main:app --reload --env-file .env

.PHONY: clean
clean:
	find . -type d -name "__pycache__" -exec rm -rf {} +
	find . -type f -name "*.pyc" -delete
	find . -type f -name "*.pyo" -delete
	find . -type f -name "*.pyd" -delete
	find . -type f -name ".coverage" -delete
	find . -type d -name "*.egg-info" -exec rm -rf {} +
	find . -type d -name "*.egg" -exec rm -rf {} +
	find . -type d -name ".pytest_cache" -exec rm -rf {} +
	find . -type d -name ".mypy_cache" -exec rm -rf {} +
	find . -type f -name ".DS_Store" -delete
	rm -rf build/
	rm -rf dist/
	rm -rf .coverage
	rm -rf htmlcov/
	rm -rf .pytest_cache/
	rm -rf .mypy_cache/

# Testing
.PHONY: test
test:
	PYTHONPATH=. pytest tests/ -v

.PHONY: test-security
test-security:
	$(PYTEST) tests/security/ -v

.PHONY: coverage
coverage:
	$(PYTEST) --cov=. tests/ --cov-report=html

# Code Quality
.PHONY: lint
lint:
	$(FLAKE8) .
	$(BLACK) . --check
	$(MYPY) .

.PHONY: format
format:
	$(BLACK) .

# Security Checks
.PHONY: security
security:
	$(BANDIT) -r . -x tests/,$(VENV)/
	$(SAFETY) check

.PHONY: security-audit
security-audit: security test-security
	@echo "Running comprehensive security audit..."
	@echo "Checking for sensitive data in git history..."
	@git log -p | grep -i "password\|secret\|key\|token" || true

# Dependencies
.PHONY: deps-update
deps-update:
	$(PIP) install -U pip
	$(PIP) install -U -r requirements.txt

.PHONY: deps-check
deps-check:
	$(SAFETY) check
	$(PIP) list --outdated

# Docker
.PHONY: docker-build
docker-build:
	docker build -t backend .

.PHONY: docker-run
docker-run:
	docker run -p 8000:8000 --env-file .env backend

# Deployment
.PHONY: deploy-check
deploy-check: lint test security
	@echo "Pre-deployment checks passed!"

.PHONY: deploy
deploy: deploy-check
	@echo "Deploying to Cloud Run..."
	gcloud run deploy

# Environment
.PHONY: env-check
env-check:
	@if [ ! -f .env ]; then \
		echo "Error: .env file not found"; \
		echo "Creating from template..."; \
		cp .env.template .env; \
	fi
	@echo "Checking required environment variables..."
	@grep -v '^#' .env.template | grep '=' | cut -d '=' -f1 | while read -r var; do \
		if ! grep -q "^$$var=" .env; then \
			echo "Warning: $$var is not set in .env file"; \
		fi \
	done

# Help
.PHONY: help
help:
	@echo "Available commands:"
	@echo "  setup          - Create virtual environment and install dependencies"
	@echo "  run            - Run development server"
	@echo "  clean          - Remove all build, test, and coverage files"
	@echo "  test           - Run all tests"
	@echo "  test-security  - Run security tests"
	@echo "  coverage       - Run tests with coverage report"
	@echo "  lint           - Run code quality checks"
	@echo "  format         - Format code with Black"
	@echo "  security       - Run security checks"
	@echo "  security-audit - Run comprehensive security audit"
	@echo "  deps-update    - Update dependencies"
	@echo "  deps-check     - Check for outdated dependencies"
	@echo "  docker-build   - Build Docker image"
	@echo "  docker-run     - Run Docker container"
	@echo "  deploy-check   - Run pre-deployment checks"
	@echo "  deploy         - Deploy to Cloud Run"
	@echo "  env-check      - Check environment variables"

.DEFAULT_GOAL := help 