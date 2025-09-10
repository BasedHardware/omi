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
    # accumulate until we have at least win_size
    while len(buf) < win_size:
        chunk, ts = inlet.pull_chunk(timeout=0.5)
        if chunk:
            # chunk: list of [samples][channels]
            buf.extend(chunk)
        if time.time() - start > timeout:
            raise TimeoutError("Timed out while waiting for LSL samples")
    # Take the last win_size samples
    arr = np.array(buf[-win_size:])  # shape [win_size, n_channels_total]
    arr = arr.T  # [n_channels_total, win_size]
    sel = np.array(use_channels, dtype=int)
    arr = arr[sel, :]
    return arr

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
        # pull raw window
        win = pull_window(inlet, fs, n_channels, win_sec=win_sec, use_channels=use_channels)
        # filter per channel
        for ch in range(win.shape[0]):
            win[ch] = bandpass(win[ch], fs)
        feats = emg_features(win)
        X.append(feats)
        y.append(label)
        print(f"{label}: {i+1}/{n_windows}")
        time.sleep(0.15)  # brief pause between windows
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
# Main
# -------------------------------
def main():
    # ------- Parameters -------
    classes = ["snap", "play", "change", "rest"]
    windows_per_class = 40
    win_sec = 0.2
    confidence_threshold = 0.8
    smooth_k = 3
    dataset_dir = "emg_datasets"
    os.makedirs(dataset_dir, exist_ok=True)

    # ------- Connect to LSL -------
    inlet, fs, n_channels, stream_name = connect_lsl_stream()
    print(f"Connected to LSL stream: {stream_name} | fs={fs} Hz | channels={n_channels}")
    use_channels = (0, 1, 2)  # << only use channels 0,1,2

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

    # ------- Real-time inference -------
    print("\n=== Real-time Classification (LSL, facial EMG) ===")
    print("Say/whisper 'snap', 'play', or 'change'. Neutral for 'rest'. Ctrl+C to stop.\n")

    smoother = MajoritySmoother(k=smooth_k)
    try:
        while True:
            # get latest window
            win = pull_window(inlet, fs, n_channels, win_sec=win_sec, use_channels=use_channels, timeout=2.0)
            for ch in range(win.shape[0]):
                win[ch] = bandpass(win[ch], fs)
            feats = emg_features(win)

            probs = clf.predict_proba([feats])[0]
            pred = clf.classes_[np.argmax(probs)]
            conf = float(np.max(probs))

            if conf > confidence_threshold:
                smoother.push(pred)
                voted = smoother.vote()
                if voted is not None:
                    print(f"Recognized: {voted} ({conf:.2f})")
            time.sleep(0.1)
    except KeyboardInterrupt:
        print("\nStopping…")

if __name__ == "__main__":
    main()
