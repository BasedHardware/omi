# Modulate Velma-2: Non-deterministic utterance ordering

## Issue

Sending the **same audio** to Modulate's Velma-2 streaming API with **identical parameters** produces utterances in **different order** across runs.

## Test audio

`test_audio.wav` — 38s, 16kHz, mono, PCM16. Contains 4 spoken utterances from LibriSpeech (public domain) separated by 5 seconds of silence:

| # | Utterance | Source |
|---|-----------|--------|
| 1 | "He hoped there would be stew for dinner, turnips and carrots..." | LibriSpeech test-clean/1089/134686/0000 |
| 2 | "Stuff it into you, his belly counselled him." | LibriSpeech test-clean/1089/134686/0001 |
| 3 | "After early nightfall the yellow lamps would light up..." | LibriSpeech test-clean/1089/134686/0002 |
| 4 | "Hello Bertie, any good in your mind?" | LibriSpeech test-clean/1089/134686/0003 |

**Download:** If the WAV is not included in your copy, download from GCS:
```bash
curl -o test_audio.wav "https://storage.googleapis.com/omi-pr-assets/modulate-repro/test_audio.wav"
```

## Reproduce

```bash
pip install websockets
export MODULATE_API_KEY=your_key_here
python repro_utterance_order.py --runs 5
```

Or pass the key directly:
```bash
python repro_utterance_order.py --api-key YOUR_KEY --runs 5
```

## Expected

All runs return utterances in order: `1→2→3→4`

## Observed

Order varies between runs. Example from 5 identical runs:

```
Run 1: [1→2→3→4] CORRECT
Run 2: [2→1→3→4] WRONG ORDER
Run 3: [2→1→3→4] WRONG ORDER
Run 4: [1→2→3→4] CORRECT
Run 5: [2→1→3→4] WRONG ORDER

Order consistency: 2/5 runs correct (40%)
```

## Impact

This non-deterministic ordering causes WER measurements on the same audio to swing wildly between runs (e.g., 5% to 75% WER on identical input) because WER is computed on the concatenated utterance text.

The `start_ms` timestamps in the returned utterances are correct — utterance 1 always has the earliest `start_ms`. But the **arrival order** over the WebSocket is not guaranteed to match the temporal order.

## API parameters used

```
wss://modulate-developer-apis.com/api/velma-2-stt-streaming
  ?speaker_diarization=true
  &partial_results=true
  &sample_rate=16000
  &audio_format=s16le
  &num_channels=1
  &language=en
```

Audio streamed in 100ms chunks (3200 bytes) at real-time pacing.
