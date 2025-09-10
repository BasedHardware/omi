import os, time
import numpy as np
import joblib
from datetime import datetime

from brainflow.board_shim import BoardShim, BrainFlowInputParams, BoardIds
from scipy.signal import butter, filtfilt
from sklearn.svm import SVC
from sklearn.model_selection import cross_val_score
from sklearn.preprocessing import StandardScaler
from sklearn.pipeline import make_pipeline

# -------------------------------
# Filtering & Features
# -------------------------------
def butter_bandpass(low, high, fs, order=4):
    b, a = butter(order, [low/(fs/2), high/(fs/2)], btype='band')
    return b, a

def bandpass(x, fs, low=20, high=450):
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
# Ganglion setup
# -------------------------------
def setup_board(serial_port=None):
    print("BrainFlow version:", BoardShim.get_version())
    params = BrainFlowInputParams()
    if serial_port:
        params.serial_port = serial_port  # required for BLED112 on macOS / Windows (COMx)
    # params.timeout = 15  # optional, default 15s
    board = BoardShim(BoardIds.GANGLION_BOARD.value, params)
    board.prepare_session()
    board.start_stream()
    return board


def teardown_board(board):
    try:
        board.stop_stream()
    finally:
        board.release_session()

# -------------------------------
# Data collection
# -------------------------------
def collect_class_windows(board, fs, emg_channels, label, n_windows=40, win_sec=0.2, settle_sec=2.5):
    """
    Collect n_windows windows for a single label.
    User mouths/whispers the word (or remains neutral for 'rest').
    """
    print(f"\n=== Prepare for: {label.upper()} ===")
    if label == "rest":
        print("Keep your face/jaw relaxed. Mouth closed. Breathe normally.")
    else:
        print(f"Mouth or whisper the word '{label}' clearly and consistently.")
    print(f"Starting in {int(settle_sec)}s ...")
    time.sleep(settle_sec)

    X, y = [], []
    win_size = int(win_sec * fs)
    count = 0
    while count < n_windows:
        data = board.get_board_data()
        if data.shape[1] < win_size:
            time.sleep(0.05)
            continue

        emg = data[emg_channels, :]
        for ch in range(emg.shape[0]):
            emg[ch] = bandpass(emg[ch], fs)

        win = emg[:, -win_size:]
        feats = emg_features(win)
        X.append(feats)
        y.append(label)
        count += 1
        print(f"{label}: {count}/{n_windows}")

        # brief pause so each window reflects a fresh articulation / rest
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
# Main
# -------------------------------
def main():
    # ------- Parameters -------
    classes = ["snap", "play", "change", "rest"]  # all facial EMG classes
    windows_per_class = 40                       # 200ms windows per class
    win_sec = 0.2                                # 200 ms analysis window
    confidence_threshold = 0.8
    smooth_k = 3                                 # majority vote over last k predictions
    dataset_dir = "emg_datasets"
    os.makedirs(dataset_dir, exist_ok=True)

    # ------- Setup board -------
    board = setup_board(serial_port="/dev/tty.usbmodem1101") # adjust for your system. on macOS, run terminal and then run the following command: ls /dev/tty.*

    try:
        fs = BoardShim.get_sampling_rate(BoardIds.GANGLION_BOARD.value)
        emg_channels = BoardShim.get_emg_channels(BoardIds.GANGLION_BOARD.value)

          # Only use channels 0, 1, 2
        emg_channels = emg_channels[:3]   # keep first three

        print("\nPlace ALL electrodes on FACE/JAW.")
        print("Suggested: CH1–CH2 masseter, CH3–CH4 chin/lips; REF=forehead; BIAS=shoulder/mastoid.\n")

        print("Stabilizing stream for 3s...")
        time.sleep(3.0)

        # ------- Collect dataset -------
        X_list, y_list = [], []
        for label in classes:
            Xc, yc = collect_class_windows(
                board, fs, emg_channels,
                label=label,
                n_windows=windows_per_class,
                win_sec=win_sec,
                settle_sec=3.0
            )
            X_list.append(Xc)
            y_list.append(yc)

        X = np.vstack(X_list)
        y = np.concatenate(y_list)

        # Save dataset
        ts = datetime.now().strftime("%Y%m%d_%H%M%S")
        npz_path = os.path.join(dataset_dir, f"face_emg_snap_play_pause_{ts}.npz")
        np.savez(npz_path, X=X, y=y, classes=np.array(classes))
        print(f"\nSaved dataset: {npz_path}")

        # ------- Train classifier -------
        clf = make_pipeline(StandardScaler(), SVC(kernel='linear', probability=True))
        scores = cross_val_score(clf, X, y, cv=5)
        print("Cross-validated accuracy:", np.mean(scores))
        clf.fit(X, y)

        model_path = "emg_face_snap_play_pause_model.pkl"
        joblib.dump(clf, model_path)
        print(f"Model saved: {model_path}")

        # ------- Real-time loop -------
        print("\n=== Real-time Classification (facial) ===")
        print("Mouth/whisper 'snap', 'play', or 'change'. Keep neutral face for 'rest'.")
        print("Press Ctrl+C to exit.\n")

        win_size = int(win_sec * fs)
        smoother = MajoritySmoother(k=smooth_k)

        while True:
            data = board.get_board_data()
            if data.shape[1] < win_size:
                time.sleep(0.03)
                continue

            emg = data[emg_channels, :]
            for ch in range(emg.shape[0]):
                emg[ch] = bandpass(emg[ch], fs)

            win = emg[:, -win_size:]
            feats = emg_features(win)

            probs = clf.predict_proba([feats])[0]
            pred = clf.classes_[np.argmax(probs)]
            conf = float(np.max(probs))

            if conf > confidence_threshold:
                smoother.push(pred)
                voted = smoother.vote()
                if voted is not None:
                    print(f"Recognized: {voted} ({conf:.2f})")
            # else: low confidence → ignore / implicit rest

            time.sleep(0.1)

    except KeyboardInterrupt:
        print("\nStopping real-time loop...")
    finally:
        teardown_board(board)
        print("Board session closed.")

if __name__ == "__main__":
    main()
