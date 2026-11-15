# Delete-account safety UI evidence

Twenty real Flutter widget rasters, 393 x 932 logical pixels at 3x (1179 x 2796),
using the approved harness, Omi theme, SF Pro fonts and iOS safe insets. Every state
is provided in light and dark: reason, feedback, pause instead, mixed/server-only/
phone-only/no pending recordings, immediate-deletion fallback, restore, and
finish-deleting confirmation. The restore fixture uses a backend wipe deadline
nine days away; its final warning appears only in the confirmation dialog. The
phone-only fixture uses seven days to verify that copy does not assume fourteen.
Grace durations and counts in these renders are synthetic fixtures; no signed-in
account or backend was contacted.

From app/: `/Users/dazheng/workspace/omi/bin/omi-heavy run -- nice flutter test --no-pub .local/render_delete_flow_test.dart`

The harness is copied beside these images. Its original local path is app/.local/;
copy it there to reproduce. It renders to /Volumes/Ephemeral/scratch/deletion-renders/v2/.
The harness passed 17 tests, and all 20 PNGs were visually inspected.

Product contract and backend integration dependency: app/docs/account-deletion.md.
