"""Checkout import for the shared logging config.

The NeMo image already imports a top-level ``utils`` package, so parakeet
cannot import ``utils.logging_config`` there. The image build copies
``backend/utils/logging_config.py`` over this file. Tests and the typechecker
import this shim, which re-exports the shared module.
"""

from utils.logging_config import configure_split_stream_logging, quiet_repetitive_nemo_logs

__all__ = ['configure_split_stream_logging', 'quiet_repetitive_nemo_logs']
