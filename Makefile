ROOT := $(shell git rev-parse --show-toplevel)
HOOKS_DIR := $(shell git rev-parse --git-path hooks)

.PHONY: setup setup-hooks

setup: setup-hooks
	@echo "Worktree setup complete."

setup-hooks:
	@mkdir -p "$(HOOKS_DIR)"
	@ln -s -f "$(ROOT)/scripts/pre-commit" "$(HOOKS_DIR)/pre-commit"
	@ln -s -f "$(ROOT)/scripts/pre-push" "$(HOOKS_DIR)/pre-push"
	@chmod +x "$(ROOT)/scripts/pre-commit" "$(ROOT)/scripts/pre-push"
	@echo "Installed Git hooks in $(HOOKS_DIR)."
