# Read a live transcript and request a recap

For users on Conversations V3, opening an eligible live detail can immediately show verified speech from this phone. Deliberately opening Summary requests the first eligible recap. A saved recap appears immediately and can be refreshed explicitly. Short conversations show recent transcript lines. Opening Transcript, browsing Home and passive detail refreshes do not invoke the live recap model.

The Firestore emulator regression in `tests/integration/test_conversations_v3_live_catchup_firestore.py` exercises concurrent lease acquisition, append during inference and same-clock correction. Internal iOS delivery is tracked on SCA-3063. See the [live conversation contract](../../listen_pusher_pipeline.mdx#live-conversation-transcript-and-recap).
