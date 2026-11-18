# Pre-coalescing worker fixtures

These are byte-for-byte `git show` snapshots from PR #25608's pre-PR main,
`f47914db8856fdb9f0be165b489e066f04088192`, of the two worker modules changed by
the PR. The `.txt` suffix preserves the reviewed old source from formatters.
`tests.support.pre_coalescing_worker` checks their SHA-256 digests and loads fresh
private modules per test, including routing the old runner's local traversal
import to the old traversal. It never replaces `sys.modules` or the new worker.
Unchanged erasure, gate, storage and query dependencies use the normal modules.

Reproduce each snapshot with:

```sh
git show f47914db8856fdb9f0be165b489e066f04088192:backend/database/conversation_batch_purge_jobs.py
git show f47914db8856fdb9f0be165b489e066f04088192:backend/database/batch_pipeline_conversation_purge.py
```

Do not update these fixtures when current worker code changes: they represent an
old deployed consumer, including its limitations, in mixed-version tests.
