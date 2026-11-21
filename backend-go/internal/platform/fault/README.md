# fault

Seeded injection points for local multi-worker and restart tests.

| Rule | Test |
| --- | --- |
| Replaying the same seed and points arms the same injection order | `TestScheduleReplaysTheSameSeededPoints` |
| An injected fault records its seed and reached point | `TestInjectionCarriesSeedAndPoint` |
