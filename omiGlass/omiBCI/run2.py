# Acquire from Ganglion, filter, extract features, and train a small classifier
import numpy as np
from brainflow.board_shim import BoardShim, BrainFlowInputParams, BoardIds
from brainflow.data_filter import DataFilter, FilterTypes, DetrendOperations
from sklearn.svm import SVC
from sklearn.model_selection import cross_val_score
from scipy.signal import butter, filtfilt

# Save for realtime use
import joblib

# --- Configure board (Ganglion) ---
params = BrainFlowInputParams()
params.serial_port = ''  # usually not needed for Ganglion BLE
board = BoardShim(BoardIds.GANGLION_BOARD.value, params)
board.prepare_session()
board.start_stream()  # start BLE stream

# --- Collect a small labeled dataset interactively (pseudo-codey) ---
fs = BoardShim.get_sampling_rate(BoardIds.GANGLION_BOARD.value)  # ~200 Hz
emg_channels = BoardShim.get_emg_channels(BoardIds.GANGLION_BOARD.value)
labels = []
X = []

clf = joblib.load("emg_word_model.pkl")

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

# --- Real-time prediction loop ---
print("Starting real-time prediction. Use your own cueing system to mouth words.")      

while True:
    data = board.get_board_data()
    if data.shape[1] == 0:
        continue
    emg_data = data[emg_channels, :]

    # Filter + window as before
    win = emg_data[:, -int(0.2*fs):]  # last 200 ms
    feats = emg_features(win)
    pred = clf.predict([feats])[0]
    conf = np.max(clf.predict_proba([feats]))
    if conf > 0.8:  # confidence threshold
        print("Recognized:", pred)
