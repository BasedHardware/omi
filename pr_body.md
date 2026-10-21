Add missing test coverage for batch_recording.dart

🎯 **What:** The tests for `batch_recording.dart` had some missing edge cases and bounds (minimum bound of 1 second, maximum bound of 24 hours, zero sample rate or frame size). Added tests for these cases in `batch_recording_test.dart` to reach 100% test coverage.
Also fixed a BuildContext async gap issue in `conversation_actions.dart`.

📊 **Coverage:** `batch_recording.dart` is fully covered.
✨ **Result:** Validated `batch_recording.dart` test coverage. Fixed CI diff hygiene issue and added changelog fragment.

UI-Evidence: none
