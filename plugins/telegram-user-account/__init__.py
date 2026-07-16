"""Telegram user-account AI Clone plugin.

Marker file so Python treats `telegram-user-account/` as a package
(this directory has a hyphen in its name, which is a non-Python
identifier, but the __init__.py makes Python happy regardless).

The plugin's actual modules (redact, simple_storage, main, telethon
client) are imported by their bare names by tests and by the
production entry point. We deliberately do NOT auto-import
submodules here — a relative import in __init__.py fails when the
plugin is loaded outside its package context (e.g., from a test that
puts the plugin dir on sys.path but not the parent plugins/ dir).
"""
