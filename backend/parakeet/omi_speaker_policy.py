"""Checkout shim; the GPU image copies the speaker policy over this module.

NeMo owns the top-level utils package in that image.
"""

from utils.speakers.policy import BATCH_CLUSTER, PARAKEET_CLUSTER

__all__ = ['BATCH_CLUSTER', 'PARAKEET_CLUSTER']
