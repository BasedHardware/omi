# Variables
SHELL := /bin/bash
FLUTTER := flutter
DART := dart
PYTHON := python3
PIP := pip3
NGROK := ngrok
UVICORN := uvicorn

# Environment files
BACKEND_ENV := backend/.env
APP_ENV := app/.dev.env

# Colors for output
GREEN := \033[0;32m
NC := \033[0m # No Color

.PHONY: help setup run-app run-backend run-ngrok install-deps clean test build-app

help:
	@echo "Available commands:"
	@echo "  make setup         - Set up both app and backend"
	@echo "  make run-app      - Run Flutter app"
	@echo "  make run-backend  - Run backend server"
	@echo "  make run-ngrok    - Run ngrok tunnel"
	@echo "  make install-deps - Install all dependencies"
	@echo "  make clean        - Clean build files"
	@echo "  make test         - Run tests"
	@echo "  make build-app    - Build Flutter app"

setup: install-deps
	@if [ ! -f $(BACKEND_ENV) ]; then \
		cp backend/.env.template $(BACKEND_ENV); \
		echo "${GREEN}Created backend/.env from template${NC}"; \
	fi
	@if [ ! -f $(APP_ENV) ]; then \
		cp app/.env.template app/.dev.env; \
		echo "${GREEN}Created app/.dev.env from template${NC}"; \
	fi
	@echo "${GREEN}Setup completed${NC}"

install-deps:
	@echo "Installing dependencies..."
	@cd app && $(FLUTTER) pub get
	@cd backend && $(PIP) install -r requirements.txt
	@echo "${GREEN}Dependencies installed${NC}"

run-app:
	@echo "Running Flutter app..."
	@cd app && $(FLUTTER) run

run-backend:
	@echo "Running backend server..."
	@cd backend && $(UVICORN) main:app --reload --env-file .env

run-ngrok:
	@echo "Starting ngrok tunnel..."
	@if [ -f $(BACKEND_ENV) ]; then \
		export $$(cat $(BACKEND_ENV) | xargs) && \
		$(NGROK) http --domain=$$NGROK_DOMAIN 8000; \
	else \
		echo "Error: $(BACKEND_ENV) not found"; \
		exit 1; \
	fi

clean:
	@echo "Cleaning..."
	@cd app && $(FLUTTER) clean
	@find . -name "*.pyc" -delete
	@find . -type d -name "__pycache__" -delete
	@echo "${GREEN}Clean completed${NC}"

test:
	@echo "Running tests..."
	@cd app && $(FLUTTER) test
	@cd backend && pytest
	@echo "${GREEN}Tests completed${NC}"

build-app:
	@echo "Building Flutter app..."
	@cd app && $(FLUTTER) build apk --release
	@echo "${GREEN}Build completed${NC}"

# Watch commands for development
watch-app:
	@echo "Running Flutter app in watch mode..."
	@cd app && $(FLUTTER) run --hot

watch-backend:
	@echo "Running backend server in watch mode..."
	@cd backend && $(UVICORN) main:app --reload --env-file .env

# Development helpers
format:
	@echo "Formatting code..."
	@cd app && $(DART) format .
	@cd backend && black .
	@echo "${GREEN}Formatting completed${NC}"

lint:
	@echo "Linting code..."
	@cd app && $(FLUTTER) analyze
	@cd backend && flake8
	@echo "${GREEN}Linting completed${NC}"
