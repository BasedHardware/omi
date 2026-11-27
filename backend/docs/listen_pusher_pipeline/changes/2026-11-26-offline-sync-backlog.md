## Offline sync backlog measurement

SCA-4753 adds an Offline sync backlog row to Omi Core Features. It shows failed
uploads, the backend-sync revision-wide HTTP 503 share, upload age over one and
six hours, and six-hour upload age by build. The upload panels count retries.
All use trailing one-hour windows.

The v2 upload handler uses the existing trace before admission. Its age
histogram now has an exact six-hour boundary and finite buckets through seven
days. The build counter exposes
exact allowlisted mobile builds plus `older` and `unknown`. Rotate that list as
mobile releases change, keeping at most six exact builds. No new stores, app
release or alert rules are part of Phase 0.
