# import librosa
# import torch
# import torchaudio
#
# from utils.endpoints import timeit
# from utils.stt.vad import retrieve_proper_segment_points
#
#
import librosa
import noisereduce as nr
import torch
import torchaudio
from pydub import effects, AudioSegment


def preprocess_audio(
        audio_path: str,
        sample_rate: int = 16000,
        save_dir: str = None,
        trim_silence: bool = True,
        trim_silence_threshold: int = 15,
        use_noise_reduce: bool = True,
        normalize_audio: bool = True,
        # perform_vad_cleaning: bool = True,
        # use_pyannote_vad: bool = False,
) -> str:
    signal, fs = torchaudio.load(audio_path)

    signal_np = signal.numpy().squeeze()
    if trim_silence:
        signal_np, _ = librosa.effects.trim(signal_np, top_db=trim_silence_threshold)
    if use_noise_reduce:
        signal_np = nr.reduce_noise(y=signal_np, sr=sample_rate)

    processed_signal = torch.tensor(signal_np).unsqueeze(0)

    # Save the intermediate processed signal
    result_audio_path = f"{save_dir}/{audio_path.split('/')[-1]}" if save_dir else audio_path
    torchaudio.save(result_audio_path, processed_signal, sample_rate)

    if normalize_audio:
        aseg = AudioSegment.from_wav(result_audio_path)
        normalizedsound = effects.normalize(aseg)
        normalizedsound.export(result_audio_path, format="wav")

    # if not perform_vad_cleaning:
    #     return result_audio_path

    # Use VAD to determine the proper segment points
    # if use_pyannote_vad:
    #     start, end = retrieve_proper_segment_points(result_audio_path)  # _pyannote
    # else:
    #     start, end = retrieve_proper_segment_points(result_audio_path)
    # if start is None or end is None:
    #     print("No speech detected in the audio.")
    #     return None

    # Convert start and end times to samples
    # start_sample = int(start * target_sample_rate)
    # end_sample = int(end * target_sample_rate)

    # Trim the audio to the VAD detected segment
    # final_signal = processed_signal[:, start_sample:end_sample]

    # Save the final processed signal
    # torchaudio.save(result_audio_path, final_signal, target_sample_rate)

    # os.remove(audio_path)
    return result_audio_path
