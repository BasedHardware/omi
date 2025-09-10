# live_openbci_brainflow_4ch_plot.py
import threading
import time
from collections import deque
import glob
import sys

import numpy as np
import matplotlib.pyplot as plt
from matplotlib.animation import FuncAnimation

from brainflow.board_shim import BoardShim, BrainFlowInputParams, BoardIds

# -------------------------------
# CONFIG
# -------------------------------
# Set your BLED112 serial port here. Example: "/dev/tty.usbmodem11" (macOS), "COM5" (Windows).
SERIAL_PORT = "/dev/tty.usbmodem11"   # <-- change if needed
# Optional: MAC address of your Ganglion (recommended if multiple devices nearby)
MAC_ADDRESS = None  # e.g. "XX:XX:XX:XX:XX:XX" or leave None to scan
BUFFER_SECS = 10     # history length on screen
REFRESH_MS = 33      # ~30 FPS

# If you prefer auto-detect of /dev/tty.usbmodem* on macOS when SERIAL_PORT is empty:
def _auto_detect_serial_port():
    ports = sorted(glob.glob("/dev/tty.usbmodem*"))
    return ports[0] if ports else None

# -------------------------------
# BrainFlow board helper
# -------------------------------
def setup_board(serial_port=None, mac_address=None):
    print("BrainFlow version:", BoardShim.get_version())
    params = BrainFlowInputParams()
    if serial_port:
        params.serial_port = serial_port
    if mac_address:
        params.mac_address = mac_address
    # params.timeout = 15  # default is 15s

    board = BoardShim(BoardIds.GANGLION_BOARD.value, params)
    board.prepare_session()
    # Use a decent internal buffer; start_stream(None) uses default 256
    board.start_stream()
    return board

def teardown_board(board):
    try:
        board.stop_stream()
    finally:
        board.release_session()

# -------------------------------
# Acquisition thread using BrainFlow
# -------------------------------
class BrainFlowReader(threading.Thread):
    def __init__(self, board, emg_chans, fs, buffer_secs=10):
        super().__init__(daemon=True)
        self.board = board
        self.emg_chans = emg_chans
        self.fs = int(fs)
        self.maxlen = int(buffer_secs * fs)
        self.running = threading.Event()
        self.running.set()
        self.buffers = [deque([0.0]*self.maxlen, maxlen=self.maxlen) for _ in emg_chans]

    def run(self):
        # Continuously grab whatever the board has buffered and append
        while self.running.is_set():
            try:
                data = self.board.get_board_data()  # clears internal buffer, shape [n_rows, n_samples]
                if data.size == 0:
                    time.sleep(0.01)
                    continue
                # Select channels of interest
                emg = data[self.emg_chans, :]  # shape [n_emg, n_samples]
                for i in range(emg.shape[0]):
                    self.buffers[i].extend(emg[i, :].tolist())
            except Exception as e:
                # Keep running even if temporary read fails
                print("read error:", e)
                time.sleep(0.05)

    def get_window(self):
        # return np.array [n_channels, n_samples]
        return np.vstack([np.asarray(buf) for buf in self.buffers])

    def stop(self):
        self.running.clear()

# -------------------------------
# Main plotting
# -------------------------------
def main():
    # Resolve serial port (auto if requested)
    serial_port = SERIAL_PORT
    if (not serial_port) or serial_port.strip().lower() in ("auto", "detect"):
        serial_port = _auto_detect_serial_port()
        if not serial_port:
            print("Could not auto-detect /dev/tty.usbmodem*. Please set SERIAL_PORT.")
            sys.exit(1)
        print(f"Auto-detected serial port: {serial_port}")

    # Setup board
    board = setup_board(serial_port=serial_port, mac_address=MAC_ADDRESS)

    try:
        fs = BoardShim.get_sampling_rate(BoardIds.GANGLION_BOARD.value)
        # For Ganglion, these are the 4 data channels
        emg_channels = BoardShim.get_eeg_channels(BoardIds.GANGLION_BOARD.value)  # typically [0,1,2,3]
        n_channels = len(emg_channels)
        print(f"Connected. fs={fs} Hz | channels={emg_channels}")

        reader = BrainFlowReader(board, emg_chans=emg_channels, fs=fs, buffer_secs=BUFFER_SECS)
        reader.start()

        # Plot setup
        fig, axes = plt.subplots(n_channels, 1, sharex=True, figsize=(10, 7))
        if n_channels == 1:
            axes = [axes]
        lines = []
        for i, ax in enumerate(axes):
            line, = ax.plot([], [], linewidth=1.0)
            lines.append(line)
            ax.set_ylabel(f"Ch {emg_channels[i]}")
            ax.grid(True, linestyle="--", linewidth=0.5, alpha=0.5)
        axes[-1].set_xlabel("Time (s)")
        fig.suptitle("OpenBCI Ganglion (BrainFlow) — Live 4-Channel Stream")

        window_secs = BUFFER_SECS
        x = np.linspace(-window_secs, 0, int(window_secs * fs))

        def init():
            for line in lines:
                line.set_data(x, np.zeros_like(x))
            for ax in axes:
                ax.set_xlim(-window_secs, 0)
                ax.set_ylim(-50, 50)  # adjust later; we auto-scale below anyway
            return lines

        def update(_frame):
            data = reader.get_window()  # [n_channels, n_samples]
            # If buffer length changed (first frames), rebuild x
            if data.shape[1] != x.size:
                # Re-compute x with the actual buffer size
                _x = np.linspace(-window_secs, 0, data.shape[1])
            else:
                _x = x
            for i in range(n_channels):
                y = data[i, :]
                lines[i].set_data(_x, y)
                # gentle auto-scale
                ymin, ymax = np.percentile(y, [1, 99])
                pad = 0.1 * (ymax - ymin + 1e-6)
                axes[i].set_ylim(ymin - pad, ymax + pad)
            return lines

        ani = FuncAnimation(fig, update, init_func=init, interval=REFRESH_MS, blit=False)

        try:
            plt.tight_layout()
            plt.show()
        except KeyboardInterrupt:
            pass
        finally:
            reader.stop()
            time.sleep(0.2)

    finally:
        teardown_board(board)
        print("Board session closed.")

if __name__ == "__main__":
    main()
