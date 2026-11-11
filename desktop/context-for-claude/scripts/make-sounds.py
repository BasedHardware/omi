#!/usr/bin/env python3
"""make-sounds.py — procedurally synthesizes every UI audio asset this app ships.

Everything here is generated from scratch with numpy + the stdlib `wave` module: no
samples, no loops, no third-party sound libraries, nothing downloaded from the network.
That means these assets carry no license of their own — they are code, not licensed
audio, so the app can ship them freely.

SHIPPED FORMAT IS ALAC-IN-.M4A, NOT .WAV — DO NOT "FIX" THIS BACK TO WAV.
The repo's root .gitignore has a deliberate, repo-wide `*.wav` rule, so raw WAV output
here can never be committed (and pad.wav alone is ~14 MB, too large for generated
content even losslessly). Every asset is therefore synthesized to WAV in a temp file
and then losslessly re-encoded to ALAC (`afconvert -f m4af -d alac`) at
Resources/Sounds/<name>.m4a, with the round-trip verified bit-exact against the
pre-encode WAV before the temp file is discarded. ALAC, not AAC: AAC's encoder
inserts priming/padding samples at the edges of the stream, which would reintroduce
exactly the loop click pad.wav's head/tail crossfade exists to eliminate. Playback
decodes each .m4a into an AVAudioPCMBuffer once, so the container costs nothing at
loop time — only sample-exactness matters, and only ALAC guarantees it here.

Run:
    python3 scripts/make-sounds.py

Output (48 kHz, 16-bit PCM, ALAC in .m4a, written to Resources/Sounds/):
    pad.m4a     — looping ambient bed for the first-run cinematic
    swoosh.m4a  — transition whoosh (windows swooping in, bar stretch, etc.)
    click.m4a   — UI click for onboarding cards / permission steps
    chime.m4a   — success cue for a granted permission and the final "all set"

Deterministic and idempotent at the audio-content level: a fixed RNG seed means
re-running this script always regenerates bit-identical *samples* (verified by
decoding the shipped .m4a back to PCM and diffing). The .m4a container bytes
themselves can differ run to run — afconvert stamps its own metadata (e.g. an
encoder timestamp atom) into the file — but the decoded audio never changes.
Requires `afconvert` (ships with macOS) on PATH; no other external tools,
downloads, or network access.
"""

import glob
import math
import os
import subprocess
import tempfile
import wave

import numpy as np

SAMPLE_RATE = 48000
FWHM_TO_SIGMA = 2.0 * math.sqrt(2.0 * math.log(2.0))

# Fixed seed so the only randomness in here (the swoosh's noise texture) is
# reproducible — re-running this script is a no-op on disk.
_rng = np.random.default_rng(1729)


# --------------------------------------------------------------------------
# Small shared helpers: gain/IO, panning, envelopes, oscillators.
# --------------------------------------------------------------------------


def db_to_lin(db):
    return 10.0 ** (db / 20.0)


def peak_normalize(signal, target_dbfs):
    """Scale `signal` so its absolute peak sits at `target_dbfs`."""
    peak = float(np.max(np.abs(signal)))
    if peak < 1e-9:
        return signal
    return signal * (db_to_lin(target_dbfs) / peak)


def pan_gains(position):
    """Equal-power pan law. position in [-1, 1], 0 = center."""
    position = max(-1.0, min(1.0, position))
    angle = (position + 1.0) * (math.pi / 4.0)
    return math.cos(angle), math.sin(angle)


def cents_to_ratio(cents):
    return 2.0 ** (cents / 1200.0)


def triangle_wave(freq, t):
    """Triangle oscillator via arcsin(sin(.)) — cheap, alias-light at these frequencies."""
    return (2.0 / math.pi) * np.arcsin(np.sin(2.0 * np.pi * freq * t))


def exp_sweep_phase_signal(n_samples, sr, f_start, f_end):
    """A sine whose instantaneous frequency glides f_start -> f_end (log/exponential),
    built by integrating instantaneous frequency into phase so the glide is click-free."""
    t = np.arange(n_samples) / sr
    duration = n_samples / sr
    frac = t / duration if duration > 0 else t
    f_t = f_start * (f_end / f_start) ** frac
    phase = 2.0 * np.pi * np.cumsum(f_t) / sr
    return np.sin(phase)


def adsr_envelope(n_samples, sr, attack_s, decay_s, sustain_level, release_s):
    """Classic attack/decay/sustain/release envelope spanning the whole buffer.
    Attack and release use a raised-cosine (smooth) curve; decay is linear."""
    t = np.arange(n_samples) / sr
    total = n_samples / sr
    a_end = attack_s
    d_end = attack_s + decay_s
    r_start = max(d_end, total - release_s)

    env = np.empty(n_samples)

    mask = t < a_end
    x = np.clip(t[mask] / max(attack_s, 1e-9), 0.0, 1.0)
    env[mask] = 0.5 * (1.0 - np.cos(np.pi * x))

    mask = (t >= a_end) & (t < d_end)
    x = np.clip((t[mask] - a_end) / max(decay_s, 1e-9), 0.0, 1.0)
    env[mask] = 1.0 - (1.0 - sustain_level) * x

    mask = (t >= d_end) & (t < r_start)
    env[mask] = sustain_level

    mask = t >= r_start
    x = np.clip((t[mask] - r_start) / max(release_s, 1e-9), 0.0, 1.0)
    env[mask] = sustain_level * 0.5 * (1.0 + np.cos(np.pi * x))

    return np.clip(env, 0.0, None)


def attack_decay_envelope(n_samples, sr, attack_s, decay_tau_s, peak_frac_of_attack=1.0, onset_sample=0):
    """Fast percussive envelope: a raised-cosine rise to a peak, then an exponential
    decay with time constant decay_tau_s — no sustain plateau.

    peak_frac_of_attack < 1.0 skews the peak earlier within the attack window (a
    "skewed-Hann" hump) instead of landing it exactly at the end of the attack.
    onset_sample lets several of these be staggered inside one shared buffer
    (used to arpeggiate chime.wav's notes).
    """
    env = np.zeros(n_samples)
    if onset_sample >= n_samples:
        return env

    local_n = n_samples - onset_sample
    t_local = np.arange(local_n) / sr
    peak_t = max(attack_s * peak_frac_of_attack, 1.0 / sr)

    rising = t_local <= peak_t
    x = np.clip(t_local[rising] / peak_t, 0.0, 1.0)
    local_env = np.empty(local_n)
    local_env[rising] = 0.5 * (1.0 - np.cos(np.pi * x))

    falling = ~rising
    local_env[falling] = np.exp(-(t_local[falling] - peak_t) / decay_tau_s)

    env[onset_sample:] = local_env
    return env


def apply_end_fade(signal, sr, fade_ms):
    """Force a clean zero at the very last sample of a one-shot buffer (exponential
    decays never truly reach zero, and a hard stop can click)."""
    fade_samples = min(int(sr * fade_ms / 1000.0), signal.shape[0])
    if fade_samples <= 0:
        return signal
    ramp = np.linspace(1.0, 0.0, fade_samples)
    out = signal.copy()
    if out.ndim == 1:
        out[-fade_samples:] *= ramp
    else:
        out[-fade_samples:] *= ramp[:, None]
    return out


def write_wav(path, samples, channels, sample_rate=SAMPLE_RATE):
    """Write float64 samples in [-1, 1] (shape (n,) mono or (n, channels)) as 16-bit PCM."""
    samples = np.clip(np.asarray(samples, dtype=np.float64), -1.0, 1.0)
    pcm = np.ascontiguousarray(np.round(samples * 32767.0).astype("<i2"))
    with wave.open(path, "wb") as wf:
        wf.setnchannels(channels)
        wf.setsampwidth(2)
        wf.setframerate(sample_rate)
        wf.writeframes(pcm.tobytes())


def read_pcm_frames(wav_path):
    """Raw PCM sample bytes from a WAV file (header-agnostic — two encoders can lay
    out chunks differently and still carry identical sample data)."""
    with wave.open(wav_path, "rb") as wf:
        return wf.readframes(wf.getnframes())


def ship_alac(name, samples, channels, out_dir, sample_rate=SAMPLE_RATE):
    """Write `samples` to a temp WAV, losslessly encode it to Resources/Sounds/<name>.m4a
    via ALAC, verify the round-trip is bit-exact, then delete the temp WAV. Raises if
    afconvert is missing/fails or if the decoded audio does not match exactly — we never
    ship a "probably fine" lossy asset."""
    fd, tmp_wav_path = tempfile.mkstemp(prefix=f"make-sounds-{name}-", suffix=".wav")
    os.close(fd)
    decoded_wav_path = None
    try:
        write_wav(tmp_wav_path, samples, channels, sample_rate)

        out_path = os.path.join(out_dir, f"{name}.m4a")
        subprocess.run(
            ["afconvert", "-f", "m4af", "-d", "alac", tmp_wav_path, out_path],
            check=True,
            capture_output=True,
            text=True,
        )

        fd2, decoded_wav_path = tempfile.mkstemp(prefix=f"make-sounds-{name}-decoded-", suffix=".wav")
        os.close(fd2)
        subprocess.run(
            ["afconvert", "-f", "WAVE", "-d", "LEI16", out_path, decoded_wav_path],
            check=True,
            capture_output=True,
            text=True,
        )

        original_pcm = read_pcm_frames(tmp_wav_path)
        decoded_pcm = read_pcm_frames(decoded_wav_path)
        if original_pcm != decoded_pcm:
            raise RuntimeError(
                f"ALAC round-trip for {name}.m4a is NOT bit-exact against the source WAV — "
                "refusing to ship a lossy loop asset. Investigate before re-running."
            )

        return out_path
    finally:
        os.remove(tmp_wav_path)
        if decoded_wav_path and os.path.exists(decoded_wav_path):
            os.remove(decoded_wav_path)


def feedback_delay_reverb(x, sr, delay_ms, tap_ms, feedback, wet, cutoff_hz, tap_gain=0.35):
    """A minimal pseudo-reverb: one feedback delay line with a one-pole low-pass sitting
    in the feedback path (so every trip around the loop gets darker), plus a single
    discrete early-reflection tap. No filter library available, so the low-pass is a
    straightforward first-order IIR (y += a*(x-y)) run inline with the delay recursion."""
    n = len(x)
    delay_samples = max(1, int(sr * delay_ms / 1000.0))
    tap_samples = int(sr * tap_ms / 1000.0)
    a = 1.0 - math.exp(-2.0 * math.pi * cutoff_hz / sr)

    xl = x.tolist()
    delay_line = [0.0] * delay_samples
    lpf_state = 0.0
    wet_out = [0.0] * n
    idx = 0
    for i in range(n):
        delayed = delay_line[idx]
        lpf_state += a * (delayed - lpf_state)
        delay_line[idx] = xl[i] + lpf_state * feedback
        wet_out[i] = delayed
        idx += 1
        if idx == delay_samples:
            idx = 0

    wet_signal = np.array(wet_out)
    if tap_samples < n:
        wet_signal[tap_samples:] += x[: n - tap_samples] * tap_gain

    return x * (1.0 - wet) + wet_signal * wet


def band_sweep_noise(n_samples, sr, f_start, f_end, q, window_ms, rng):
    """White noise band-passed through a Gaussian magnitude mask whose centre frequency
    sweeps f_start -> f_end, via overlap-add STFT: window, FFT, multiply by a Gaussian
    mask centred at f(t) with width set by Q, inverse FFT, overlap-add (normalized by
    the summed window so gain stays flat regardless of overlap factor)."""
    win_len = int(round(sr * window_ms / 1000.0))
    win_len += win_len % 2
    win_len = max(win_len, 16)
    hop = max(win_len // 2, 1)

    window = np.hanning(win_len)
    noise = rng.standard_normal(n_samples)
    freqs = np.fft.rfftfreq(win_len, d=1.0 / sr)
    duration = n_samples / sr

    out = np.zeros(n_samples + win_len)
    win_sum = np.zeros(n_samples + win_len)

    start = 0
    while start < n_samples:
        end = start + win_len
        segment = np.zeros(win_len)
        avail = min(win_len, n_samples - start)
        segment[:avail] = noise[start : start + avail]
        windowed = segment * window

        center_t = (start + win_len / 2.0) / sr
        frac = min(max(center_t / duration, 0.0), 1.0)
        f_center = f_start * (f_end / f_start) ** frac

        spectrum = np.fft.rfft(windowed)
        sigma = max(f_center / q, 20.0) / FWHM_TO_SIGMA
        mask = np.exp(-0.5 * ((freqs - f_center) / sigma) ** 2)
        shaped = np.fft.irfft(spectrum * mask, n=win_len)

        out[start:end] += shaped
        win_sum[start:end] += window
        start += hop

    win_sum[win_sum < 1e-6] = 1.0
    return (out / win_sum)[:n_samples]


# --------------------------------------------------------------------------
# One function per sound.
# --------------------------------------------------------------------------


def make_pad():
    """~24s stereo ambient bed: four detuned/panned partial pairs (sine + quiet
    octave-up triangle), one shared ADSR + slow amplitude LFO, a feedback-delay
    pseudo-reverb, then a crossfaded loop point so numberOfLoops = -1 is seamless.

    24s (not the doc's 60-90s) is a deliberate size trade-off: even losslessly
    encoded, a 60-90s bed is too large to commit as generated content. The seam
    math (crossfade width, envelope shape) is unaffected by total length."""
    loop_len_s = 24.0  # shortened from the doc's 60-90s to keep the shipped asset small
    crossfade_s = 2.0
    n_raw = int((loop_len_s + crossfade_s) * SAMPLE_RATE)
    t = np.arange(n_raw) / SAMPLE_RATE

    partials_hz = [130.81, 196.00, 261.63, 329.63]  # C3, G3, C4, E4
    detune_cents = [4.0, 3.5, 4.5, 3.8]  # 3-5 cents per pair
    pan_amount = [0.18, 0.16, 0.20, 0.15]  # 15-20%
    triangle_gain = 0.28  # "quiet" octave-up double
    voice_gain = 1.0 / len(partials_hz)

    left = np.zeros(n_raw)
    right = np.zeros(n_raw)

    for f0, cents, pan_amt in zip(partials_hz, detune_cents, pan_amount):
        ratio = cents_to_ratio(cents)
        f_lo, f_hi = f0 / ratio, f0 * ratio

        voice_lo = (np.sin(2.0 * np.pi * f_lo * t) + triangle_gain * triangle_wave(f_lo * 2.0, t)) * voice_gain
        voice_hi = (np.sin(2.0 * np.pi * f_hi * t) + triangle_gain * triangle_wave(f_hi * 2.0, t)) * voice_gain

        gl_lo, gr_lo = pan_gains(-pan_amt)
        gl_hi, gr_hi = pan_gains(pan_amt)
        left += voice_lo * gl_lo + voice_hi * gl_hi
        right += voice_lo * gr_lo + voice_hi * gr_hi

    env = adsr_envelope(n_raw, SAMPLE_RATE, attack_s=3.0, decay_s=1.0, sustain_level=0.7, release_s=4.0)
    lfo = 1.0 + 0.10 * np.sin(2.0 * np.pi * 0.07 * t)  # 0.05-0.1 Hz amplitude LFO
    total_env = env * lfo
    left *= total_env
    right *= total_env

    left = feedback_delay_reverb(left, SAMPLE_RATE, delay_ms=390.0, tap_ms=180.0, feedback=0.40, wet=0.27, cutoff_hz=5000.0)
    right = feedback_delay_reverb(
        right, SAMPLE_RATE, delay_ms=430.0, tap_ms=180.0, feedback=0.40, wet=0.27, cutoff_hz=5000.0
    )
    raw = np.stack([left, right], axis=-1)

    loop_samples = int(loop_len_s * SAMPLE_RATE)
    crossfade_samples = int(crossfade_s * SAMPLE_RATE)
    head = raw[:crossfade_samples]
    tail = raw[loop_samples : loop_samples + crossfade_samples]
    x = np.linspace(0.0, 1.0, crossfade_samples)
    fade_in = np.sin(x * np.pi / 2.0)[:, None]  # equal-power crossfade
    fade_out = np.cos(x * np.pi / 2.0)[:, None]
    blended = head * fade_in + tail * fade_out

    looped = np.concatenate([blended, raw[crossfade_samples:loop_samples]], axis=0)
    looped = peak_normalize(looped, -6.0)

    # Extra return values are unused by main(); they let verification tooling rebuild
    # the pre-crossfade ("naive loop") buffer without duplicating this function.
    return looped, raw, loop_samples, crossfade_samples


def make_swoosh():
    """250-400ms whoosh: band-passed noise sweeping 400 Hz -> ~3.5 kHz (STFT magnitude
    shaping) plus a quiet 150->600 Hz chirp underneath, with a fast skewed-Hann attack
    and an exponential decay to silence."""
    duration_s = 0.32
    n = int(duration_s * SAMPLE_RATE)

    band_left = band_sweep_noise(n, SAMPLE_RATE, 400.0, 3500.0, q=3.0, window_ms=30.0, rng=_rng)
    band_right = band_sweep_noise(n, SAMPLE_RATE, 400.0, 3500.0, q=3.0, window_ms=30.0, rng=_rng)
    chirp = exp_sweep_phase_signal(n, SAMPLE_RATE, 150.0, 600.0) * 0.18

    env = attack_decay_envelope(n, SAMPLE_RATE, attack_s=0.015, decay_tau_s=0.09, peak_frac_of_attack=0.40)

    left = (band_left + chirp) * env
    right = (band_right + chirp) * env
    stereo = np.stack([left, right], axis=-1)

    stereo = apply_end_fade(stereo, SAMPLE_RATE, fade_ms=8.0)
    stereo = peak_normalize(stereo, -9.0)  # spec: -8 to -10 dBFS
    return stereo


def make_click():
    """40-80ms mono UI click: a 1 kHz tick pitch-bending down to 700 Hz over a quieter
    300-400 Hz body, fast attack, fast exponential decay, no sustain."""
    duration_s = 0.06
    n = int(duration_s * SAMPLE_RATE)
    t = np.arange(n) / SAMPLE_RATE

    tick = exp_sweep_phase_signal(n, SAMPLE_RATE, 1000.0, 700.0)
    body = np.sin(2.0 * np.pi * 350.0 * t) * 0.30

    env = attack_decay_envelope(n, SAMPLE_RATE, attack_s=0.002, decay_tau_s=0.010, peak_frac_of_attack=1.0)

    signal = (tick + body) * env
    signal = apply_end_fade(signal, SAMPLE_RATE, fade_ms=4.0)
    signal = peak_normalize(signal, -12.0)
    return signal


def make_chime():
    """Success cue: a short bell-like arpeggio in C major (C5-G5-E5) — consonant with
    the pad's C3/G3/C4/E4 chord — gentle attack, no sustain plateau, tail under 1.2s."""
    duration_s = 1.15
    n = int(duration_s * SAMPLE_RATE)
    t = np.arange(n) / SAMPLE_RATE

    notes = [
        (523.25, 0.000, 0.00),  # C5, center
        (783.99, 0.070, 0.35),  # G5, slightly right
        (659.25, 0.140, -0.30),  # E5, slightly left
    ]
    attack_s, decay_tau_s = 0.006, 0.30

    left = np.zeros(n)
    right = np.zeros(n)
    for freq, onset_s, pan in notes:
        onset_sample = int(onset_s * SAMPLE_RATE)
        env = attack_decay_envelope(n, SAMPLE_RATE, attack_s, decay_tau_s, peak_frac_of_attack=1.0, onset_sample=onset_sample)
        bell = (
            np.sin(2.0 * np.pi * freq * t)
            + 0.25 * np.sin(2.0 * np.pi * freq * 2.0 * t)
            + 0.12 * np.sin(2.0 * np.pi * freq * 3.0 * t)
        )
        voice = bell * env
        gl, gr = pan_gains(pan)
        left += voice * gl
        right += voice * gr

    stereo = np.stack([left, right], axis=-1)
    stereo = apply_end_fade(stereo, SAMPLE_RATE, fade_ms=25.0)
    stereo = peak_normalize(stereo, -9.0)
    return stereo


def main():
    out_dir = os.path.normpath(os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "Resources", "Sounds"))
    os.makedirs(out_dir, exist_ok=True)

    # This directory ships ALAC .m4a only — the repo gitignores *.wav repo-wide, so
    # any stray .wav here (e.g. left over from before this script switched formats)
    # can never be committed. Sweep it clean on every run.
    for stale_wav in glob.glob(os.path.join(out_dir, "*.wav")):
        os.remove(stale_wav)

    pad_samples, _raw, _loop_samples, _crossfade_samples = make_pad()
    swoosh_samples = make_swoosh()
    click_samples = make_click()
    chime_samples = make_chime()

    ship_alac("pad", pad_samples, channels=2, out_dir=out_dir)
    ship_alac("swoosh", swoosh_samples, channels=2, out_dir=out_dir)
    ship_alac("click", click_samples, channels=1, out_dir=out_dir)
    ship_alac("chime", chime_samples, channels=2, out_dir=out_dir)

    print(f"Wrote pad.m4a, swoosh.m4a, click.m4a, chime.m4a (ALAC) to {out_dir}")


if __name__ == "__main__":
    main()
