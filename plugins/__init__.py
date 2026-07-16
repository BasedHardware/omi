"""Omi chat-platform plugins (Telegram / WhatsApp / iMessage / user-account).

This package is the umbrella for all the AI Clone's chat-platform
plugins. Each plugin is a self-hosted FastAPI service that the
desktop app talks to over HTTP. The plugins share code via the
plugins/_shared/ subpackage (persona_client, auth, plugin_discovery,
etc.).

A plugin's directory layout (see plugins/omi-telegram-app/ for the
canonical bot-API example, and plugins/telegram-user-account/ for
the user-API variant):

    plugins/<plugin-name>/
        main.py              FastAPI service
        simple_storage.py    per-plugin user config + ring buffer
        <client>.py          outbound HTTP / Telethon wrapper
        requirements.txt
        runtime.txt
        Dockerfile            optional
        test/                 pytest tests, one TestClient-based file
                             per behavior under test
        pytest.ini           pythonpath so tests can `from plugins.<plugin>...`

The `pythonpath = .` in pytest.ini is required because the plugin
sits at plugins/<name>/ but its tests use `from plugins.<name>...`.
Without the pythonpath addition, pytest's default collection would
not find the parent `plugins/` package on sys.path.
"""
