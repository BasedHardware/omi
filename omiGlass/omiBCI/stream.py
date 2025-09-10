# live_openbci_lsl_4ch_plot.py
import argparse
import threading
import time
from collections import deque

import numpy as np
import matplotlib.pyplot as plt
from matplotlib.animation import FuncAnimation
from pylsl import StreamInlet, resolve_byprop

# -------------------------------
# LSL connect
# -------------------------------
def connect_lsl_stream(name="OpenBCI_EEG", timeout=10):
    streams = resolve_byprop('name', name, timeout=timeout)
    if not streams:
        streams = resolve_byprop('type', 'EEG', timeout=timeout)
        if not streams:
            raise RuntimeError("No LSL EEG streams found. Is the OpenBCI LSL streamer running (/start)?")
    info = streams[0]
    inlet = StreamInlet(info, max_buflen=60)
    fs = int(round(info.nominal_srate())) if info.nominal_srate() > 0 else 200
    n_channels = info.channel_count()
    print(f"Connected to LSL: {info.name()} | fs={fs} Hz | channels={n_channels}")
    return inlet, fs, n_channels

# -------------------------------
# Acquisition thread
# -------------------------------
class LSLReader(threading.Thread):
    def __init__(self, inlet, n_channels, buffer_secs=10):
        super().__init__(daemon=True)
        self.inlet = inlet
        self.n_channels = n_channels
        self.fs = int(round(inlet.info().nominal_srate())) if inlet.info().nominal_srate() > 0 else 200
        self.maxlen = int(buffer_secs * self.fs)
        self.buffers = [deque([0.0]*self.maxlen, maxlen=self.maxlen) for _ in range(self.n_channels)]
        self.running = threading.Event()
        self.running.set()

    def run(self):
        while self.running.is_set():
            chunk, _ = self.inlet.pull_chunk(timeout=0.2)
            if not chunk:
                continue
            arr = np.asarray(chunk)
            if arr.ndim != 2 or arr.shape[1] < self.n_channels:
                continue
            for ch in range(self.n_channels):
                self.buffers[ch].extend(arr[:, ch])

    def get_window(self):
        return np.vstack([np.asarray(buf) for buf in self.buffers])

    def stop(self):
        self.running.clear()

# -------------------------------
# Main plotting
# -------------------------------
def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--name", default="OpenBCI_EEG", help="LSL stream name hint")
    ap.add_argument("--window", type=float, default=10.0, help="seconds of history to display")
    ap.add_argument("--fps", type=float, default=30, help="plot refresh rate (frames/sec)")
    args = ap.parse_args()

    inlet, fs, n_channels_total = connect_lsl_stream(name=args.name)
    use_channels = list(range(min(4, n_channels_total)))  # first 4 channels
    print(f"Displaying channels: {use_channels}")

    reader = LSLReader(inlet, n_channels=n_channels_total, buffer_secs=args.window)
    reader.start()

    fig, axes = plt.subplots(len(use_channels), 1, sharex=True, figsize=(10, 7))
    if len(use_channels) == 1:
        axes = [axes]

    lines = []
    for i, ax in enumerate(axes):
        line, = ax.plot([], [], linewidth=1.0)
        lines.append(line)
        ax.set_ylabel(f"Ch {use_channels[i]}")
        ax.grid(True, linestyle="--", linewidth=0.5, alpha=0.5)
    axes[-1].set_xlabel("Time (s)")
    fig.suptitle("OpenBCI via LSL — Live 4-Channel Stream")

    # Precompute x axis (seconds); will adjust if buffer size changes
    window_secs = args.window
    x = np.linspace(-window_secs, 0, int(window_secs * fs))

    def init():
        for line in lines:
            line.set_data(x, np.zeros_like(x))
        for ax in axes:
            ax.set_xlim(-window_secs, 0)
            ax.set_ylim(-50, 50)
        return lines

    def update(_frame):
        data = reader.get_window()  # [n_total_ch, n_samples]
        # ensure x matches current buffer length
        n = data.shape[1]
        _x = x if x.size == n else np.linspace(-window_secs, 0, n)
        for i, ch in enumerate(use_channels):
            y = data[ch, :]
            lines[i].set_data(_x, y)
            ymin, ymax = np.percentile(y, [1, 99])
            pad = 0.1 * (ymax - ymin + 1e-6)
            axes[i].set_ylim(ymin - pad, ymax + pad)
        return lines

    ani = FuncAnimation(fig, update, init_func=init, interval=1000/args.fps, blit=False)

    try:
        plt.tight_layout()
        plt.show()
    except KeyboardInterrupt:
        pass
    finally:
        reader.stop()
        time.sleep(0.2)

if __name__ == "__main__":
    main()
