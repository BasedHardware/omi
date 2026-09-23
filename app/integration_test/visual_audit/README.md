# Mobile visual inspection

Repeatable screenshots of **production Flutter widgets**, driven by taps and
text entry in `flutter-tester`, using the existing seeded journey bootstrap.
No login, signing, simulator, customer data or external API is required.
This complements `agent-flutter` / flow-walker for live device inspection; it
is not another acceptance-journey runner or native-device qualification.

From a fresh task worktree, run `make lane-bootstrap`, then:

```bash
cd app
bash integration_test/visual_audit/capture.sh
# Or choose a NEW output directory outside Git:
bash integration_test/visual_audit/capture.sh /tmp/my-mobile-audit
```

The command emits numbered PNGs, `frames.json` (actions, visible text and target
sizes), an HTML gallery, source identity/hashes and a test log. Re-run after changing a scenario or UI;
open and inspect every PNG before accepting it. Nonzero exit means incomplete
capture. Fonts are loaded from the app assets and pinned Flutter
SDK, instead of Flutter tests' Ahem placeholder glyphs.

Coverage: memory list/create/empty-save/save/edit/no-search-results/filtered-empty/recovery; task
create/draft/date-picker/quick-date/failed-save/retry; conversation summary; chat
new-user and existing-data starters/editable selection/draft/reply/copy; recording source sheet. Task and recording sheets use a
neutral host; their surrounding home navigation is outside this capture lane.

Constraints: 390×844 logical pixels, Android/Roboto theme metrics, 2× PNGs,
English dark theme. The theme mirrors `main.dart`; keep it synchronized when
changing that theme. Backend, authentication, storage and platform boundaries
are synthetic. HTTP is restricted to `127.0.0.1` before a connection is made.
The existing fixture backend app-search response logs a missing `hasNext`
warning; marketplace results and installed-app selection are not audited.
The reply's `[srv-reply-…]` suffix is fixture provenance, not product copy.

There is no native keyboard, status bar, safe-area inset, BLE, audio, physical
haptic feedback, real network timing or screen reader here. Do not infer those
from the images or treat this as an installed-app test. Use the live tooling
in `app/e2e/SKILL.md` for those claims. Screenshots and logs stay outside Git.
