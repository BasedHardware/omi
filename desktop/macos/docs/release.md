# Desktop release

Normal path: merge `main` → the daily `Build Desktop Release Candidate` workflow creates one immutable tag → trusted qualification promotes that exact artifact to Beta automatically.

If a signed, qualified candidate did not reach Beta, run **Recover Qualified Desktop Beta** with `release_tag`, `confirm=recover-beta`, and a short `reason`. The backend rechecks immutable evidence, qualification, admission state, and the pointer transaction; the workflow run is the recovery audit record.

To make that exact current Beta candidate Stable, run **Promote Qualified Desktop Stable** with `release_tag` and `confirm=promote-stable`. It reads the current pointer, uses its generation for the atomic transition, and verifies the published pointer, hashes, and appcast. It only changes the desktop Stable channel; backend production deployment remains a separate approval plane.

Do not edit release bodies, pointers, static routes, or legacy bridges manually.
