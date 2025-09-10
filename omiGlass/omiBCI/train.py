import os, time
import numpy as np
import joblib
from datetime import datetime
from pylsl import StreamInlet, resolve_byprop
from scipy.signal import butter, filtfilt
from sklearn.svm import SVC
from sklearn.model_selection import cross_val_score
from sklearn.preprocessing import StandardScaler
from sklearn.pipeline import make_pipeline

# NEW: for live & final visualizations
import matplotlib.pyplot as plt

# -------------------------------
# Filtering & Features
# -------------------------------
from scipy.signal import butter, filtfilt

def butter_bandpass(low, high, fs, order=4, safety=0.95):
    """
    Designs a stable bandpass for given fs.
    - If high is None, default to min(90 Hz, 0.45*fs) (good for EMG at fs≈200)
    - Clamps cutoffs to (0, Nyquist) and ensures low < high
    """
    nyq = fs / 2.0
    if high is None:
        high = min(90.0, nyq * 0.9)  # default top cutoff
    # clamp to valid range
    low = max(1e-3, float(low))
    high = min(float(high), nyq * safety)  # keep some headroom to avoid 1.0
    if high <= low:
        # fall back to a reasonable band near the top
        high = min(max(low + 1.0, nyq * 0.45), nyq * safety)
    Wn = [low / nyq, high / nyq]
    if not (0.0 < Wn[0] < Wn[1] < 1.0):
        raise ValueError(f"Invalid normalized band: {Wn} at fs={fs}")
    b, a = butter(order, Wn, btype='band')
    return b, a

def bandpass(x, fs, low=20, high=None):
    b, a = butter_bandpass(low, high, fs)
    return filtfilt(b, a, x)

def emg_features(win, zc_thresh=0.01):
    """
    win: array [n_channels, n_samples]
    Returns concatenated features per channel: [RMS, MAV, WL, ZC, SSC]
    """
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
# LSL setup
# -------------------------------
def connect_lsl_stream(name_hint="OpenBCI_EEG", timeout=10):
    # Prefer exact name if present, else fall back to type='EEG'
    streams = resolve_byprop('name', name_hint, timeout=timeout)
    if not streams:
        streams = resolve_byprop('type', 'EEG', timeout=timeout)
        if not streams:
            raise RuntimeError("No LSL EEG streams found. Is user.py running with --add streamer_lsl and /start?")
    info = streams[0]
    inlet = StreamInlet(info, max_buflen=60)
    fs = int(round(info.nominal_srate())) if info.nominal_srate() > 0 else 200  # Ganglion ~200 Hz
    n_channels = info.channel_count()
    return inlet, fs, n_channels, info.name()

# -------------------------------
# Data collection from LSL
# -------------------------------
def pull_window(inlet, fs, n_channels, win_sec=0.2, use_channels=(0,1,2), timeout=5.0):
    """
    Pulls enough samples from LSL to fill a window of win_sec, returns [n_channels, n_samples]
    Only keeps channels in use_channels (order preserved).
    """
    win_size = int(win_sec * fs)
    buf = []
    start = time.time()
    while len(buf) < win_size:
        chunk, ts = inlet.pull_chunk(timeout=0.5)
        if chunk:
            buf.extend(chunk)  # chunk: list of [samples][channels]
        if time.time() - start > timeout:
            raise TimeoutError("Timed out while waiting for LSL samples")
    arr = np.array(buf[-win_size:])  # shape [win_size, n_channels_total]
    arr = arr.T                      # [n_channels_total, win_size]
    sel = np.array(use_channels, dtype=int)
    return arr[sel, :]

def collect_class_windows_lsl(inlet, fs, n_channels, label, n_windows=40, win_sec=0.2, settle_sec=2.5, use_channels=(0,1,2)):
    print(f"\n=== Prepare for: {label.upper()} ===")
    if label == "rest":
        print("Keep your face/jaw relaxed. Mouth closed. Breathe normally.")
    else:
        print(f"Mouth or whisper the word '{label}' clearly and consistently.")
    print(f"Starting in {int(settle_sec)}s ...")
    time.sleep(settle_sec)

    X, y = [], []
    for i in range(n_windows):
        win = pull_window(inlet, fs, n_channels, win_sec=win_sec, use_channels=use_channels)
        for ch in range(win.shape[0]):
            win[ch] = bandpass(win[ch], fs)
        feats = emg_features(win)
        X.append(feats)
        y.append(label)
        print(f"{label}: {i+1}/{n_windows}")
        time.sleep(0.15)
    return np.vstack(X), np.array(y)

# -------------------------------
# Majority-vote smoother (optional)
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
        if not self.buf: return None
        vals, counts = np.unique(self.buf, return_counts=True)
        return vals[np.argmax(counts)]

# -------------------------------
# Live bar plot helpers
# -------------------------------
def init_live_prob_plot(class_names):
    """Create a live-updating bar chart for class probabilities."""
    fig, ax = plt.subplots(figsize=(6.2, 3.2))
    bars = ax.bar(class_names, np.zeros(len(class_names)))
    texts = []
    for b in bars:
        x = b.get_x() + b.get_width()/2
        texts.append(ax.text(x, 0.01, "0.00", ha="center", va="bottom", fontsize=9))
    ax.set_ylim(0, 1.0)
    ax.set_ylabel("P(class)")
    ax.set_title("Live Class Probabilities")
    ax.grid(True, axis='y', linestyle='--', linewidth=0.5, alpha=0.5)
    plt.tight_layout()
    plt.ion()
    plt.show(block=False)
    return fig, ax, bars, texts

def update_live_prob_plot(bars, texts, probs):
    """Update bar heights and labels."""
    top = max(1.0, float(np.max(probs)) + 0.05)
    for b, t, p in zip(bars, texts, probs):
        b.set_height(float(p))
        t.set_text(f"{float(p):.2f}")
        t.set_y(float(p) + 0.02 * top)
    bars[0].axes.set_ylim(0, top)
    # Allow UI to breathe; small pause is enough
    plt.pause(0.001)

def final_visualization(prob_history, class_names, pred_history):
    """
    Show:
      - Probability traces over time for each class
      - Histogram of predicted label counts
    """
    if not prob_history:
        print("No probability history to visualize.")
        return
    times = np.array([t for (t, _) in prob_history])
    probs_mat = np.vstack([p for (_, p) in prob_history])  # [T, C]

    fig, (ax1, ax2) = plt.subplots(2, 1, figsize=(8.5, 7.5))
    # 1) Probability traces
    for ci, cname in enumerate(class_names):
        ax1.plot(times - times[0], probs_mat[:, ci], label=cname, linewidth=1.5)
    ax1.set_xlabel("Time (s)")
    ax1.set_ylabel("Probability")
    ax1.set_title("Per-class Probabilities Over Time")
    ax1.set_ylim(0, 1.0)
    ax1.grid(True, linestyle="--", linewidth=0.5, alpha=0.6)
    ax1.legend(loc="upper right")

    # 2) Predicted counts
    if len(pred_history) > 0:
        labels, counts = np.unique(np.array(pred_history), return_counts=True)
        ax2.bar(labels, counts)
        ax2.set_ylabel("Count")
        ax2.set_title("Predicted Label Counts (Smoothed)")
        ax2.grid(True, axis="y", linestyle="--", linewidth=0.5, alpha=0.6)
    else:
        ax2.text(0.5, 0.5, "No predictions above threshold", ha="center", va="center")
        ax2.set_axis_off()

    plt.tight_layout()
    plt.show()

# -------------------------------
# Main
# -------------------------------
def main():
    # ------- Parameters -------
    classes = ["cat", "rest"]
    windows_per_class = 40
    win_sec = 0.2
    confidence_threshold = 0.8
    smooth_k = 3
    dataset_dir = "emg_datasets"
    os.makedirs(dataset_dir, exist_ok=True)

    # ------- Connect to LSL -------
    inlet, fs, n_channels, stream_name = connect_lsl_stream()
    print(f"Connected to LSL stream: {stream_name} | fs={fs} Hz | channels={n_channels}")
    use_channels = (0, 1, 2)  # only use channels 0,1,2 for features

    # ------- Collect dataset -------
    X_list, y_list = [], []
    for label in classes:
        Xc, yc = collect_class_windows_lsl(
            inlet, fs, n_channels,
            label=label,
            n_windows=windows_per_class,
            win_sec=win_sec,
            settle_sec=3.0,
            use_channels=use_channels
        )
        X_list.append(Xc)
        y_list.append(yc)

    X = np.vstack(X_list)
    y = np.concatenate(y_list)

    # Save dataset
    ts = datetime.now().strftime("%Y%m%d_%H%M%S")
    npz_path = os.path.join(dataset_dir, f"face_emg_lsl_3ch_{ts}.npz")
    np.savez(npz_path, X=X, y=y, classes=np.array(classes))
    print(f"\nSaved dataset: {npz_path}")

    # ------- Train classifier -------
    clf = make_pipeline(StandardScaler(), SVC(kernel='linear', probability=True))
    scores = cross_val_score(clf, X, y, cv=5)
    print("Cross-validated accuracy:", np.mean(scores))
    clf.fit(X, y)

    model_path = "emg_face_lsl_3ch_model.pkl"
    joblib.dump(clf, model_path)
    print(f"Model saved: {model_path}")

    # ------- Real-time inference (with live probability bars) -------
    print("\n=== Real-time Classification (LSL, facial EMG) ===")
    print("Say/whisper 'cat'. Neutral for 'rest'. Ctrl+C to stop.\n")

    # Live bar setup using the trained class order
    class_names = list(clf.classes_)
    fig, ax, bars, texts = init_live_prob_plot(class_names)

    # History buffers for final visualization
    t0 = time.time()
    prob_history = []   # list of (t, probs)
    pred_history = []   # list of smoothed predictions (above threshold)
    smoother = MajoritySmoother(k=smooth_k)

    try:
        while True:
            win = pull_window(inlet, fs, n_channels, win_sec=win_sec, use_channels=use_channels, timeout=2.0)
            for ch in range(win.shape[0]):
                win[ch] = bandpass(win[ch], fs)
            feats = emg_features(win)

            probs = clf.predict_proba([feats])[0]  # aligned to clf.classes_
            pred_idx = int(np.argmax(probs))
            pred = class_names[pred_idx]
            conf = float(probs[pred_idx])

            # Append to history
            prob_history.append((time.time() - t0, probs.copy()))

            if conf > confidence_threshold:
                smoother.push(pred)
                voted = smoother.vote()
                if voted is not None:
                    pred_history.append(voted)
                    print(f"Recognized: {voted} ({conf:.2f})")

            # Update live bars
            update_live_prob_plot(bars, texts, probs)

            # If the user closed the bar figure, exit loop gracefully
            if not plt.fignum_exists(fig.number):
                break

            time.sleep(0.05)  # ~20 Hz update
    except KeyboardInterrupt:
        print("\nStopping…")
    finally:
        # Show final visualization of the session
        try:
            final_visualization(prob_history, class_names, pred_history)
        except Exception as e:
            print(f"Final visualization skipped: {e}")

if __name__ == "__main__":
    main()
