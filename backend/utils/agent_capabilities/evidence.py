"""Session evidence snapshots; roles never enter product fingerprints."""


class EvidenceRecords(dict):
    """Roles live outside storage snapshots so Review fingerprints stay intact."""

    def __init__(self, records=(), *, targets=None):
        super().__init__(records)
        self.targets = set(self if targets is None else targets)
