Synthetic fixtures contain a 120 ms, 440 Hz stereo tone at 48 kHz, no user speech.
WAV uses mono 16 kHz to keep its uncompressed size below 4 KB.
Create with FFmpeg (replace codec/extension: libopus/ogg or webm, aac/m4a or mp4,
alac/caf, pcm_s16le/wav, libmp3lame/mp3):

```sh
ffmpeg -f lavfi -i sine=frequency=440:sample_rate=48000:duration=0.12 -ac 2 -c:a libopus voice.ogg
```

`photo.heic`: `pillow_heif.register_heif_opener()` then
`PIL.Image.new('RGB', (16, 12), (220, 100, 30)).save('photo.heic')`.
The MP4 fixture includes a tiny blue video frame (lavfi color=c=blue:s=16x16:r=10:d=0.12,
libx264/yuv420p) and the stereo tone; extraction uses its first audio stream.
Container-shape tests run real FFmpeg on the tiny tones and bypass speech detection;
the STT response uses the normalized `text`/`timestamp`/`speaker` shape.

`speech.ogg` is 2.9 KB of synthesized “Hello, how are you?” (no user recording):

```sh
say -o /tmp/omi-messaging-speech.aiff 'Hello, how are you?'
ffmpeg -nostdin -hide_banner -loglevel error -y -i /tmp/omi-messaging-speech.aiff -ac 1 -ar 16000 -c:a libopus -b:a 16k speech.ogg
```

Its end-to-end regression runs real FFmpeg, local Silero VAD, provider routing,
Parakeet response normalization, and app word postprocessing. Only database
language preferences and the STT HTTP response are synthetic; no network is used.
