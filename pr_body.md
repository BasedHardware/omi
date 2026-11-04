🎯 **What:** Modified `app/lib/utils/audio/wav_bytes.dart` to support PCM16 and correctly handle PCM8 audio encoding.
💡 **Why:** Improved support for audio formats by introducing `sampleWidth` considerations in `getUInt8ListBytes` and `convertToLittleEndianBytes`. When `codec == BleAudioCodec.pcm8`, samples are correctly extracted as 8-bit, whereas before they were incorrectly reconstructed as 16-bit. PCM16 is now officially supported instead of having a `TODO: try pcm16` comment.
✅ **Verification:** Ran tests locally to verify that there are no syntax errors and format matches correctly.
✨ **Result:** Better maintainability of `wav_bytes.dart` functions with less magic numbers and more robust decoding paths for different `BleAudioCodec`s.

UI-Evidence: none
