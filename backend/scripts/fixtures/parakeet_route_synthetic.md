Synthetic qualification corpus: no user or recorded human audio.

Generated locally with macOS `say -v Samantha -r 190` from:
`The blue bird sings. [[slnc 900]] We test the audio route.`
Converted using ffmpeg to 16 kHz mono PCM16 WAV, then appended two seconds of
silence for streaming VAD emission before finalize. Size: 174,114 bytes; duration
5.4396875 seconds. No runtime TTS executable, download, model or credential needed.
The probe emits the WAV SHA-256 in every receipt. This tests route/protocol
qualification; it is not an accuracy benchmark or a throughput qualification.
