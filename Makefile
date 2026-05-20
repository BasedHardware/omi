# Hybrid local development (desktop local daemon + Omi Dev app).
# See desktop/local-backend/docs/local-mvp-runbook.md

.PHONY: help serve-local down-local local-asr-fixture

help:
	@echo "Hybrid local development targets:"
	@echo "  make serve-local   Start omi-local-backend + Omi Dev (tmux when available)"
	@echo "  make down-local    Stop tmux session, daemon, and dev desktop app"
	@echo "  make local-asr-fixture"
	@echo "                     Build a production-shaped Local Whisper fixture manifest"
	@echo ""
	@echo "Optional env: OMI_LOCAL_DAEMON_URL, OMI_LOCAL_BACKEND_DATA_DIR,"
	@echo "              OMI_HYBRID_LOCAL_TMUX_SESSION (default: omi-hybrid-local)"
	@echo "              OMI_HYBRID_LOCAL_ATTACH=0  start tmux detached"
	@echo "              OMI_LOCAL_ASR_PYTHON       Python with mlx-whisper for local ASR fixture"
	@echo "              OMI_LOCAL_ASR_FIXTURE_DIR  fixture output dir (default: /tmp/omi-local-asr-fixture)"

serve-local:
	@bash "$(CURDIR)/scripts/hybrid-local.sh" up

down-local:
	@bash "$(CURDIR)/scripts/hybrid-local.sh" down

local-asr-fixture:
	@bash "$(CURDIR)/desktop/local-asr-addon/build_dev_fixture.sh"
