"""The stage vocabulary a projection is composed against.

Ten stations of the Hero's Journey, used as an index into the archetypal layer. The
correspondence is a translation and the seams are real: Campbell's arc advances through
numbered stations while Jung's individuation spirals and repeats, and the alchemical sequence
(nigredo -> albedo -> citrinitas -> rubedo) is the load-bearing part of the mapping. This
module carries only the vocabulary — the selector ranks into it and the image layer composes
against it. What each stage means for the image, and why, is `archetypes.py`.
"""

from __future__ import annotations

from enum import Enum


class ProjectionStage(str, Enum):
    CALL = 'call'
    REFUSAL = 'refusal'
    THRESHOLD = 'threshold'
    TESTS = 'tests'
    APPROACH = 'approach'
    ORDEAL = 'ordeal'
    REWARD = 'reward'
    ROAD_BACK = 'road_back'
    RESURRECTION = 'resurrection'
    ELIXIR = 'elixir'


STAGE_NAMES: dict[ProjectionStage, str] = {
    ProjectionStage.CALL: 'Call to Adventure',
    ProjectionStage.REFUSAL: 'Refusal of the Call',
    ProjectionStage.THRESHOLD: 'Crossing the First Threshold',
    ProjectionStage.TESTS: 'Tests, Allies, and Enemies',
    ProjectionStage.APPROACH: 'Approach to the Inmost Cave',
    ProjectionStage.ORDEAL: 'The Ordeal',
    ProjectionStage.REWARD: 'The Reward',
    ProjectionStage.ROAD_BACK: 'The Road Back',
    ProjectionStage.RESURRECTION: 'The Resurrection',
    ProjectionStage.ELIXIR: 'Return with the Elixir',
}
