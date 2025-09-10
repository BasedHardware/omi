import time
import numpy as np
import joblib
from brainflow.board_shim import BoardShim, BrainFlowInputParams, BoardIds
from scipy.signal import butter, filtfilt
from sklearn.svm import SVC
from sklearn.model_selection import cross_val_score
from sklearn.preprocessing import StandardScaler
from sklearn.pipeline import make_pipeline

# -------------------------------
# Helper functions
# -------------------------------
def butter_bandpass(low, high, fs, order=4):
    b, a = butter(order, [low / (fs / 2), high / (fs / 2)], btype='band')
    return b, a

def bandpass(x, fs, low=20, high=450):
    b, a = butter_bandpass(low, high, fs)
    return filtfilt(b, a, x)

def emg_features(win, zc_thresh=0.01):
    feats = []
    for ch in range(win.shape[0]):
        x = win[ch]
        rms = np.sqrt(np.mean(x ** 2))
        mav = np.mean(np.abs(x))
        wl = np.sum(np.abs(np.diff(x)))
        zc = np.sum(((x[:-1] * x[1:]) < 0) &
                    (np.abs(x[:-1] - x[1:]) > zc_thresh))
        dx = np.diff(x)
        ssc = np.sum((dx[:-1] * dx[1:]) < 0)
        feats.extend([rms, mav, wl, zc, ssc])
    return np.array(feats, dtype=float)

# -------------------------------
# Setup Ganglion
# -------------------------------
print("BrainFlow version:", BoardShim.get_version())
params = BrainFlowInputParams()
params.serial_port = ''   # not usually needed for Ganglion BLE
board = BoardShim(BoardIds.GANGLION_BOARD.value, params)
board.prepare_session()
board.start_stream()
fs = BoardShim.get_sampling_rate(BoardIds.GANGLION_BOARD.value)
emg_channels = BoardShim.get_emg_channels(BoardIds.GANGLION_BOARD.value)

# -------------------------------
# Data Collection
# -------------------------------
classes = ["snap", "play", "rest"]
samples_per_class = 40  # number of 200ms windows per class
X, labels = [], []

win_size = int(0.2 * fs)  # 200 ms window

print("\n=== Data Collection ===")
print("You will be prompted for each class. Perform the action until counter is full.\n")

for c in classes:
    print(f"Get ready for: {c}")
    time.sleep(3)

    count = 0
    while count < samples_per_class:
        data = board.get_board_data()
        if data.shape[1] < win_size:
            continue

        emg_data = data[emg_channels, :]
        for ch in range(emg_data.shape[0]):
            emg_data[ch] = bandpass(emg_data[ch], fs)

        win = emg_data[:, -win_size:]
        feats = emg_features(win)
        X.append(feats)
        labels.append(c)
        count += 1
        print(f"{c}: {count}/{samples_per_class}")

print("Data collection complete!")

# -------------------------------
# Train Classifier
# -------------------------------
X = np.vstack(X)
y = np.array(labels)

clf = make_pipeline(StandardScaler(), SVC(kernel='linear', probability=True))
scores = cross_val_score(clf, X, y, cv=5)
print("Cross-validated accuracy:", np.mean(scores))

clf.fit(X, y)
joblib.dump(clf, "emg_snap_play_model.pkl")
print("Model saved as emg_snap_play_model.pkl")

# -------------------------------
# Real-time Classification
# -------------------------------
print("\n=== Real-time Classification ===")
print("Press Ctrl+C to exit.\n")

try:
    while True:
        data = board.get_board_data()
        if data.shape[1] < win_size:
            continue

        emg_data = data[emg_channels, :]
        for ch in range(emg_data.shape[0]):
            emg_data[ch] = bandpass(emg_data[ch], fs)

        win = emg_data[:, -win_size:]
        feats = emg_features(win)

        pred = clf.predict([feats])[0]
        conf = np.max(clf.predict_proba([feats]))
        if conf > 0.8:  # confidence threshold
            print(f"Recognized: {pred} ({conf:.2f})")

        time.sleep(0.1)

except KeyboardInterrupt:
    print("Stopping...")
finally:
    board.stop_stream()
    board.release_session()
