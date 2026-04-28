# Manual QA: Advanced Ambient Capture

1. Enable Advanced Ambient Capture in Developer / Experimental Settings.
2. Start advanced capture.
3. Lock the phone, speak for 5 minutes, and confirm the foreground notification remains visible.
4. Confirm PCM frames enter WAL and transcription works when raw audio upload is enabled.
5. Disable network, speak for 5 minutes, re-enable network, and confirm WAL sync later.
6. Open Teams, Zoom, or Meet and confirm high-risk state.
7. Start a phone call and confirm call/communication state, not normal recording.
8. Trigger another recorder and confirm silence/deprioritization detection.
9. Enable Private Mode and confirm capture/upload stops locally.
10. Revoke the selected plugin controller and confirm policy control fails closed.
11. Expire a policy and confirm it is rejected.
12. Confirm BLE Omi hardware recording still works.
13. Confirm existing normal phone mic recording still works.
14. Confirm iOS build is unaffected.

Persistent notification and Android microphone privacy indicators must remain visible whenever native capture is active.
