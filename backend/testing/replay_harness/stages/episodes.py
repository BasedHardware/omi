"""Reserved boundary after titling; episode selection coverage belongs to WP5+."""

from testing.replay_harness.stages.base import NotImplementedStage


class EpisodesDriver(NotImplementedStage):
    def __init__(self):
        super().__init__('episodes')
