# Acquire from Ganglion, filter, extract features, and train a small classifier
import numpy as np
from brainflow.board_shim import BoardShim, BrainFlowInputParams, BoardIds
from brainflow.data_filter import DataFilter, FilterTypes, DetrendOperations
from sklearn.svm import SVC
from sklearn.model_selection import cross_val_score
from scipy.signal import butter, filtfilt

print("BrainFlow version:", BoardShim.get_version())

# --- Configure board (Ganglion) ---
params = BrainFlowInputParams()
params.serial_port = ''  # usually not needed for Ganglion BLE
board = BoardShim(BoardIds.GANGLION_BOARD.value, params)
board.prepare_session()
board.start_stream()  # start BLE stream

# --- Helper filters ---
def butter_bandpass(low, high, fs, order=4):
    b, a = butter(order, [low/(fs/2), high/(fs/2)], btype='band')
    return b, a

def bandpass(x, fs, low=20, high=450):
    b, a = butter_bandpass(low, high, fs)
    return filtfilt(b, a, x)

def emg_envelope(x, fs, lp=5):  # rectified then LPF for envelope
    x = np.abs(x)
    b, a = butter(4, lp/(fs/2), btype='low')
    return filtfilt(b, a, x)

# --- Feature extraction on a window: RMS, MAV, WL, ZC, SSC ---
def emg_features(win, zc_thresh=0.01):
    feats = []
    for ch in range(win.shape[0]):
        x = win[ch]
        rms = np.sqrt(np.mean(x**2))
        mav = np.mean(np.abs(x))
        wl  = np.sum(np.abs(np.diff(x)))

        # zero crossings with threshold
        zc = np.sum(((x[:-1] * x[1:]) < 0) & (np.abs(x[:-1]-x[1:]) > zc_thresh))

        # slope sign changes
        dx = np.diff(x)
        ssc = np.sum((dx[:-1]*dx[1:]) < 0)

        feats.extend([rms, mav, wl, zc, ssc])
    return np.array(feats, dtype=float)

# --- Collect a small labeled dataset interactively (pseudo-codey) ---
fs = BoardShim.get_sampling_rate(BoardIds.GANGLION_BOARD.value)  # ~200 Hz
emg_channels = BoardShim.get_emg_channels(BoardIds.GANGLION_BOARD.value)
labels = []
X = []

print("Collecting data... Press Ctrl+C when done. Use your own cueing system to mouth words.")
try:
    # Example scheme: record for ~60s and label externally OR implement a cue loop.
    import time
    start = time.time()
    while True:
        data = board.get_board_data()  # pull buffered samples
        if data.shape[1] == 0:
            continue

        emg_data = data[emg_channels, :]

        # Band-pass filter each channel
        for ch in range(emg_data.shape[0]):
            emg_data[ch] = bandpass(emg_data[ch], fs)

        # Sliding windowing
        win_size = int(0.2 * fs)   # 200 ms window
        step     = int(0.1 * fs)   # 100 ms hop
        for start in range(0, emg_data.shape[1] - win_size, step):
            win = emg_data[:, start:start+win_size]
            feats = emg_features(win)

            # TODO: supply the current label for this segment
            # Example: labels come from your own cue script / manual annotation
            current_label = "UP"  # replace dynamically
            X.append(feats)
            labels.append(current_label)

except KeyboardInterrupt:
    print("Stopped collection.")
finally:
    board.stop_stream()
    board.release_session()

# --- Train classifier ---
from sklearn.preprocessing import StandardScaler
from sklearn.pipeline import make_pipeline

clf = make_pipeline(StandardScaler(), SVC(kernel='linear', probability=True))
X = np.vstack(X)
y = np.array(labels)

scores = cross_val_score(clf, X, y, cv=5)
print("CV accuracy:", np.mean(scores))

# Fit final model
clf.fit(X, y)

# Save for realtime use
import joblib
joblib.dump(clf, "emg_word_model.pkl")
