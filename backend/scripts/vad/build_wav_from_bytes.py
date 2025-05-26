import wave


def rebuild_wav_from_bytes(file_path, output_wav):
    with open(file_path, 'r') as f:
        audio_hex_strings = f.readlines()

    audio_bytes = bytearray()
    for line in audio_hex_strings:
        audio_bytes.extend(bytes.fromhex(line.strip()))

    # Create a WAV file
    with wave.open(output_wav, 'wb') as wf:
        wf.setnchannels(1)  # Mono channel
        wf.setsampwidth(2)  # Sample width (2 byte = 16 bits)
        wf.setframerate(8000)  # 8kHz sample rate
        wf.writeframes(audio_bytes)


if __name__ == "__main__":
    rebuild_wav_from_bytes("audio_bytes.txt", "output_0.wav")
