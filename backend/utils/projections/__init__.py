"""Projections — a generated image carrying one grounded imperative.

The public surface of the package. `generation` composes the two halves: `evidence` gathers
what the projection is selected from, and `selector` decides what it is about.
"""

from utils.projections.evidence import EvidencePacket, EvidenceTier
from utils.projections.errors import NoProjectionSubject
from utils.projections.generation import generate_projection
from utils.projections.storage import local_projection_image_path

__all__ = [
    'EvidencePacket',
    'EvidenceTier',
    'NoProjectionSubject',
    'generate_projection',
    'local_projection_image_path',
]
