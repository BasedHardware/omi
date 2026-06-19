"""
Fake external dependencies for hermetic e2e testing.

Each module provides a drop-in replacement for a real external service,
configured at the network boundary so the real backend code exercises its
full client/parsing/retry logic.
"""
