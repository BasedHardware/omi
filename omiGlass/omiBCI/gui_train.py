# emg_gui_lsl.py
import os
import threading
import time
from collections import deque
from datetime import datetime
import tkinter as tk
from tkinter import ttk, messagebox

import numpy as np
import matplotlib
matplotlib.use("TkAgg")
import matplotlib.pyplot as plt
from matplotlib.animation import FuncAnimation
from matplotlib.backends.backend_tkagg import FigureCanvasTkAgg

from pylsl import StreamInlet, resolve_byprop
from scipy.signal import butter, filtfilt
from sklearn.svm import SVC
from sklearn.model_selection import cross_val_score
from sklearn.preprocessing import StandardScaler
from sklearn.pipeline import make_pipeline
import joblib

# -------------------------------
# Filtering & Features (Nyquist-safe)
# -------------------------------
def butter_bandpass(low, high, fs, order=4, safety=0.95):
    nyq = fs / 2.0
    if high is None:
        high = min(90.0, nyq * 0.9)
    low = max(1e-3, float(low))
    high = min(float(high), nyq * safety)
    if high <= low:
        high = min(max(low + 1.0, nyq * 0.45), nyq * safety)
    Wn = [low / nyq, high / nyq]
    if not (0.0 < Wn[0] < Wn[1] < 1.0):
        raise ValueError(f"Invalid normalized band: {Wn} at fs={fs}")
    b, a = butter(order, Wn, btype='band')
    return b, a

def bandpass(x, fs, low=20, high=None, ba=None):
    if ba is None:
        b, a = butter_bandpass(low, high, fs)
    else:
        b, a = ba
    return filtfilt(b, a, x)

def emg_features(win, zc_thresh=0.01):
    feats = []
    for ch in range(win.shape[0]):
        x = win[ch]
        rms = np.sqrt(np.mean(x**2))
        mav = np.mean(np.abs(x))
        wl  = np.sum(np.abs(np.diff(x)))
        zc  = np.sum(((x[:-1] * x[1:]) < 0) & (np.abs(x[:-1] - x[1:]) > zc_thresh))
        dx  = np.diff(x)
        ssc = np.sum((dx[:-1] * dx[1:]) < 0)
        feats.extend([rms, mav, wl, zc, ssc])
    return np.array(feats, dtype=float)

# -------------------------------
# LSL helpers
# -------------------------------
def connect_lsl_stream(name_hint="OpenBCI_EEG", timeout=10):
    streams = resolve_byprop('name', name_hint, timeout=timeout)
    if not streams:
        streams = resolve_byprop('type', 'EEG', timeout=timeout)
        if not streams:
            raise RuntimeError("No LSL EEG streams found. Is the LSL streamer running (/start)?")
    info = streams[0]
    inlet = StreamInlet(info, max_buflen=60)
    fs = int(round(info.nominal_srate())) if info.nominal_srate() > 0 else 200
    n_channels = info.channel_count()
    return inlet, fs, n_channels, info.name()

class LSLReader(threading.Thread):
    def __init__(self, inlet, n_channels, fs, buffer_secs=10):
        super().__init__(daemon=True)
        self.inlet = inlet
        self.n_channels = n_channels
        self.fs = fs
        self.maxlen = int(buffer_secs * fs)
        self.buffers = [deque([0.0]*self.maxlen, maxlen=self.maxlen) for _ in range(n_channels)]
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

def pull_window(inlet, fs, n_channels, win_sec=0.2, use_channels=(0,1,2), timeout=5.0):
    win_size = int(win_sec * fs)
    buf = []
    start = time.time()
    while len(buf) < win_size:
        chunk, _ = inlet.pull_chunk(timeout=0.5)
        if chunk:
            buf.extend(chunk)
        if time.time() - start > timeout:
            raise TimeoutError("Timed out while waiting for LSL samples")
    arr = np.array(buf[-win_size:])     # [win, total_ch]
    arr = arr.T                         # [total_ch, win]
    sel = np.array(use_channels, dtype=int)
    return arr[sel, :]

# -------------------------------
# Smoother
# -------------------------------
class MajoritySmoother:
    def __init__(self, k=3):
        self.k = k
        self.buf = []
    def push(self, label):
        self.buf.append(label)
        if len(self.buf) > self.k:
            self.buf.pop(0)
    def vote(self):
        if not self.buf:
            return None
        vals, counts = np.unique(self.buf, return_counts=True)
        return vals[np.argmax(counts)]

# -------------------------------
# GUI App
# -------------------------------
class EMGApp(tk.Tk):
    def __init__(self):
        super().__init__()
        self.title("EMG via LSL – Train & Infer")
        self.geometry("1100x750")

        # State
        self.inlet = None
        self.fs = None
        self.n_channels = None
        self.stream_name = None
        self.reader = None
        self.anim = None
        self.dataset_dir = "emg_datasets"
        os.makedirs(self.dataset_dir, exist_ok=True)

        self.bpf_ba = None  # (b,a) designed after connect
        self.use_channels = (0,1,2)  # for features
        self.show_channels = None    # for plotting (set on connect)

        self.X = None
        self.y = None
        self.clf = None
        self.smoother = MajoritySmoother(k=3)
        self.conf_threshold = 0.8
        self.stop_infer = threading.Event()

        self._build_ui()
        self._build_plot()

    # ---------- UI ----------
    def _build_ui(self):
        frm = ttk.Frame(self)
        frm.pack(side=tk.LEFT, fill=tk.Y, padx=10, pady=10)

        # Connection settings
        ttk.Label(frm, text="LSL stream name:").grid(row=0, column=0, sticky="w")
        self.stream_entry = ttk.Entry(frm, width=24)
        self.stream_entry.insert(0, "OpenBCI_EEG")  # name hint; raw vs filt still OK
        self.stream_entry.grid(row=0, column=1, sticky="w", pady=2)

        ttk.Label(frm, text="Feature channels (comma):").grid(row=1, column=0, sticky="w")
        self.ch_entry = ttk.Entry(frm, width=24)
        self.ch_entry.insert(0, "0,1,2")
        self.ch_entry.grid(row=1, column=1, sticky="w", pady=2)

        self.connect_btn = ttk.Button(frm, text="Connect LSL", command=self.on_connect)
        self.connect_btn.grid(row=2, column=0, columnspan=2, sticky="we", pady=6)

        self.status_lbl = ttk.Label(frm, text="Status: idle", foreground="#444")
        self.status_lbl.grid(row=3, column=0, columnspan=2, sticky="w", pady=4)

        ttk.Separator(frm).grid(row=4, column=0, columnspan=2, sticky="we", pady=8)

        # Collection settings
        ttk.Label(frm, text="Classes (comma):").grid(row=5, column=0, sticky="w")
        self.classes_entry = ttk.Entry(frm, width=24)
        self.classes_entry.insert(0, "snap,play,change,rest")
        self.classes_entry.grid(row=5, column=1, sticky="w", pady=2)

        ttk.Label(frm, text="Windows / class:").grid(row=6, column=0, sticky="w")
        self.nwin_entry = ttk.Entry(frm, width=24)
        self.nwin_entry.insert(0, "40")
        self.nwin_entry.grid(row=6, column=1, sticky="w", pady=2)

        ttk.Label(frm, text="Win sec:").grid(row=7, column=0, sticky="w")
        self.winsec_entry = ttk.Entry(frm, width=24)
        self.winsec_entry.insert(0, "0.2")
        self.winsec_entry.grid(row=7, column=1, sticky="w", pady=2)

        ttk.Label(frm, text="Settle sec:").grid(row=8, column=0, sticky="w")
        self.settle_entry = ttk.Entry(frm, width=24)
        self.settle_entry.insert(0, "3.0")
        self.settle_entry.grid(row=8, column=1, sticky="w", pady=2)

        self.collect_btn = ttk.Button(frm, text="Collect Dataset", command=self.on_collect, state="disabled")
        self.collect_btn.grid(row=9, column=0, columnspan=2, sticky="we", pady=6)

        self.progress = ttk.Progressbar(frm, mode="determinate", length=220)
        self.progress.grid(row=10, column=0, columnspan=2, sticky="we", pady=4)

        ttk.Separator(frm).grid(row=11, column=0, columnspan=2, sticky="we", pady=8)

        # Train / Infer
        self.train_btn = ttk.Button(frm, text="Train Model", command=self.on_train, state="disabled")
        self.train_btn.grid(row=12, column=0, columnspan=2, sticky="we", pady=6)

        ttk.Label(frm, text="Confidence threshold:").grid(row=13, column=0, sticky="w")
        self.conf_entry = ttk.Entry(frm, width=24)
        self.conf_entry.insert(0, "0.8")
        self.conf_entry.grid(row=13, column=1, sticky="w", pady=2)

        self.infer_btn = ttk.Button(frm, text="Start Inference", command=self.on_infer, state="disabled")
        self.infer_btn.grid(row=14, column=0, columnspan=2, sticky="we", pady=6)

        self.stop_btn = ttk.Button(frm, text="Stop Inference", command=self.on_stop_infer, state="disabled")
        self.stop_btn.grid(row=15, column=0, columnspan=2, sticky="we", pady=2)

        ttk.Separator(frm).grid(row=16, column=0, columnspan=2, sticky="we", pady=8)

        # Prediction display
        self.pred_var = tk.StringVar(value="—")
        ttk.Label(frm, text="Prediction:").grid(row=17, column=0, sticky="w")
        self.pred_lbl = ttk.Label(frm, textvariable=self.pred_var, font=("Helvetica", 16, "bold"))
        self.pred_lbl.grid(row=17, column=1, sticky="w")

        # Log
        ttk.Label(frm, text="Log:").grid(row=18, column=0, sticky="w", pady=(10,0))
        self.log = tk.Text(frm, height=10, width=38)
        self.log.grid(row=19, column=0, columnspan=2, sticky="we")
        self.log.configure(state="disabled")

        for i in range(2):
            frm.grid_columnconfigure(i, weight=0)

    def _build_plot(self):
        # Right side: 4 stacked subplots sharing x with unified y-scale
        right = ttk.Frame(self)
        right.pack(side=tk.RIGHT, fill=tk.BOTH, expand=True, padx=10, pady=10)

        self.fig, self.axes = plt.subplots(4, 1, sharex=True, figsize=(8.5, 6.2))
        self.lines = [ax.plot([], [], linewidth=1.0)[0] for ax in self.axes]
        for i, ax in enumerate(self.axes):
            ax.set_ylabel(f"Ch {i}")
            ax.grid(True, linestyle="--", linewidth=0.5, alpha=0.5)
        self.axes[-1].set_xlabel("Time (s)")
        self.fig.suptitle("LSL Stream – Live Plot (Unified Y-Scale)")

        self.canvas = FigureCanvasTkAgg(self.fig, master=right)
        self.canvas.get_tk_widget().pack(fill=tk.BOTH, expand=True)

        self.window_secs = 10.0
        self.fs_plot = 200  # will update on connect
        self.x = np.linspace(-self.window_secs, 0, int(self.window_secs * self.fs_plot))

    def log_line(self, s):
        self.log.configure(state="normal")
        self.log.insert("end", s + "\n")
        self.log.configure(state="disabled")
        self.log.see("end")

    # ---------- Handlers ----------
    def on_connect(self):
        try:
            name_hint = self.stream_entry.get().strip()
            inlet, fs, n_ch, sname = connect_lsl_stream(name_hint=name_hint or "OpenBCI_EEG", timeout=10)
            self.inlet, self.fs, self.n_channels, self.stream_name = inlet, fs, n_ch, sname
            self.status_lbl.configure(text=f"Status: connected to {sname} | fs={fs} Hz | ch={n_ch}")
            self.log_line(f"Connected LSL: {sname} | fs={fs} | channels={n_ch}")

            # Feature channels
            self.use_channels = tuple(int(x.strip()) for x in self.ch_entry.get().split(",") if x.strip() != "")
            if any(ch < 0 or ch >= n_ch for ch in self.use_channels):
                raise ValueError(f"Invalid feature channels {self.use_channels} for stream with {n_ch} channels")

            # Design bandpass once
            self.bpf_ba = butter_bandpass(20, None, self.fs)

            # Reader + plot
            self.reader = LSLReader(self.inlet, n_channels=self.n_channels, fs=self.fs, buffer_secs=self.window_secs)
            self.reader.start()
            self.fs_plot = self.fs
            self.window_secs = 10.0
            self.x = np.linspace(-self.window_secs, 0, int(self.window_secs * self.fs_plot))
            # Which channels to show: first 4 (or fewer)
            n_show = min(4, self.n_channels)
            self.show_channels = list(range(n_show))

            def init():
                for i, line in enumerate(self.lines):
                    line.set_data(self.x, np.zeros_like(self.x))
                    if i >= n_show:
                        self.axes[i].set_visible(False)
                    else:
                        self.axes[i].set_visible(True)
                for ax in self.axes:
                    ax.set_xlim(-self.window_secs, 0)
                    ax.set_ylim(-50, 50)
                return self.lines

            def update(_):
                if self.reader is None:
                    return self.lines
                data = self.reader.get_window()  # [total_ch, n]
                n = data.shape[1]
                _x = self.x if self.x.size == n else np.linspace(-self.window_secs, 0, n)

                # set data for visible channels
                for i, ch in enumerate(self.show_channels):
                    y = data[ch, :]
                    self.lines[i].set_data(_x, y)

                # unified y-scale across visible channels
                if self.show_channels:
                    y_all = data[self.show_channels, :].reshape(-1)
                    ymin, ymax = np.percentile(y_all, [1, 99])
                    pad = 0.1 * (ymax - ymin + 1e-9)
                    ylo, yhi = (ymin - pad, ymax + pad) if np.isfinite(ymin) and np.isfinite(ymax) else (-1.0, 1.0)
                    for i, ax in enumerate(self.axes):
                        if i < len(self.show_channels):
                            ax.set_ylim(ylo, yhi)
                return self.lines

            # Start animation
            if self.anim:
                self.anim.event_source.stop()
            self.anim = FuncAnimation(self.fig, update, init_func=init, interval=33, blit=False)
            self.canvas.draw()

            # Enable next actions
            self.collect_btn.configure(state="normal")
            self.train_btn.configure(state="normal")
        except Exception as e:
            messagebox.showerror("Connect error", str(e))
            self.log_line(f"[ERROR] connect: {e}")

    def on_collect(self):
        if not self.inlet:
            messagebox.showwarning("Not connected", "Connect to an LSL stream first.")
            return
        try:
            classes = [c.strip() for c in self.classes_entry.get().split(",") if c.strip()]
            nwin = int(self.nwin_entry.get())
            win_sec = float(self.winsec_entry.get())
            settle = float(self.settle_entry.get())
        except Exception as e:
            messagebox.showerror("Bad parameters", str(e))
            return

        self.collect_btn.configure(state="disabled")
        self.train_btn.configure(state="disabled")
        self.infer_btn.configure(state="disabled")
        self.progress.configure(value=0, maximum=nwin * len(classes))
        self.status_lbl.configure(text="Status: collecting dataset…")
        self.log_line(f"Collecting dataset: classes={classes} nwin={nwin} win_sec={win_sec}")

        def worker():
            X_list, y_list = [], []
            try:
                for label in classes:
                    self.log_line(f"=== Prepare for: {label.upper()} ===")
                    if label.lower() == "rest":
                        self.log_line("Relax face/jaw. Mouth closed. Breathe normally.")
                    else:
                        self.log_line(f"Say/whisper '{label}' clearly and consistently.")
                    self.log_line(f"Starting in {int(settle)}s …")
                    time.sleep(settle)

                    for i in range(nwin):
                        win = pull_window(self.inlet, self.fs, self.n_channels, win_sec=win_sec, use_channels=self.use_channels)
                        # Filter per channel using predesigned bpf
                        for ch in range(win.shape[0]):
                            win[ch] = bandpass(win[ch], self.fs, ba=self.bpf_ba)
                        feats = emg_features(win)
                        X_list.append(feats)
                        y_list.append(label)
                        self.progress.step(1)
                        self.status_lbl.configure(text=f"Status: {label} {i+1}/{nwin}")
                        self.update_idletasks()
                        time.sleep(0.15)

                X = np.vstack(X_list)
                y = np.array(y_list)
                ts = datetime.now().strftime("%Y%m%d_%H%M%S")
                npz_path = os.path.join(self.dataset_dir, f"face_emg_lsl_3ch_{ts}.npz")
                np.savez(npz_path, X=X, y=y, classes=np.array(classes))
                self.log_line(f"Saved dataset: {npz_path}")
                self.X, self.y = X, y
                self.status_lbl.configure(text="Status: dataset collected")
            except Exception as e:
                self.log_line(f"[ERROR] collect: {e}")
                messagebox.showerror("Collect error", str(e))
            finally:
                self.collect_btn.configure(state="normal")
                self.train_btn.configure(state="normal")

        threading.Thread(target=worker, daemon=True).start()

    def on_train(self):
        if self.X is None or self.y is None:
            messagebox.showwarning("No data", "Collect a dataset first.")
            return

        def worker():
            try:
                self.status_lbl.configure(text="Status: training…")
                self.log_line("Training SVC (linear)…")
                clf = make_pipeline(StandardScaler(), SVC(kernel='linear', probability=True))
                scores = cross_val_score(clf, self.X, self.y, cv=5)
                self.log_line(f"Cross-validated accuracy: {np.mean(scores):.3f}")
                clf.fit(self.X, self.y)
                self.clf = clf

                model_path = "emg_face_lsl_3ch_model.pkl"
                joblib.dump(clf, model_path)
                self.log_line(f"Model saved: {model_path}")
                self.status_lbl.configure(text="Status: trained")
                self.infer_btn.configure(state="normal")
            except Exception as e:
                self.log_line(f"[ERROR] train: {e}")
                messagebox.showerror("Train error", str(e))

        threading.Thread(target=worker, daemon=True).start()

    def on_infer(self):
        if not self.clf:
            messagebox.showwarning("No model", "Train a model first.")
            return
        try:
            self.conf_threshold = float(self.conf_entry.get())
        except:
            self.conf_threshold = 0.8
            self.conf_entry.delete(0, tk.END)
            self.conf_entry.insert(0, "0.8")

        self.stop_infer.clear()
        self.infer_btn.configure(state="disabled")
        self.stop_btn.configure(state="normal")
        self.status_lbl.configure(text="Status: inferring…")
        self.log_line("Starting real-time inference…")

        def worker():
            try:
                while not self.stop_infer.is_set():
                    win = pull_window(self.inlet, self.fs, self.n_channels, win_sec=0.2, use_channels=self.use_channels, timeout=2.0)
                    for ch in range(win.shape[0]):
                        win[ch] = bandpass(win[ch], self.fs, ba=self.bpf_ba)
                    feats = emg_features(win)

                    probs = self.clf.predict_proba([feats])[0]
                    classes = self.clf.classes_
                    pred_idx = int(np.argmax(probs))
                    pred, conf = classes[pred_idx], float(probs[pred_idx])

                    if conf > self.conf_threshold:
                        self.smoother.push(pred)
                        voted = self.smoother.vote()
                        if voted is not None:
                            self.pred_var.set(f"{voted} ({conf:.2f})")
                    else:
                        # below threshold; don't change display
                        pass
                    time.sleep(0.1)
            except Exception as e:
                self.log_line(f"[ERROR] infer: {e}")
                messagebox.showerror("Inference error", str(e))
            finally:
                self.infer_btn.configure(state="normal")
                self.stop_btn.configure(state="disabled")
                self.status_lbl.configure(text="Status: idle")

        threading.Thread(target=worker, daemon=True).start()

    def on_stop_infer(self):
        self.stop_infer.set()

    def destroy(self):
        try:
            if self.anim:
                self.anim.event_source.stop()
            if self.reader:
                self.reader.stop()
                time.sleep(0.2)
        finally:
            super().destroy()

if __name__ == "__main__":
    app = EMGApp()
    app.mainloop()
