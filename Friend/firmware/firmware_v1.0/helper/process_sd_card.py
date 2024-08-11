import os
import numpy as np
import wave

# Define parameters
CODEC = "mulaw"  # Use "pcm" if you suspect PCM data; "mulaw" otherwise
SAMPLE_RATE = 8000  # Sample rate for the audio
SAMPLE_WIDTH = 2  # 16-bit audio
CHANNELS = 1  # Mono audio

# Function to read the PCM data from a single .txt file
def read_pcm_data(filepath):
    with open(filepath, 'rb') as file:
        data = file.read().decode('ISO-8859-1').split(',')
        audio_data = bytearray()
        for value in data:
            try:
                audio_data.append(int(value.strip()))
            except ValueError:
                continue
    return audio_data

# Function to join PCM data from all .txt files in the directory
def join_pcm_data(directory):
    all_pcm_data = bytearray()
    for filename in sorted(os.listdir(directory)):
        if filename.endswith(".txt"):
            filepath = os.path.join(directory, filename)
            pcm_data = read_pcm_data(filepath)
            all_pcm_data.extend(pcm_data)
    return all_pcm_data

# Function to decode µ-law encoded data to PCM
def ulaw2linear(ulaw_byte):
    """Convert a µ-law byte to a 16-bit linear PCM value."""
    # Define the lookup table for the exponent
    EXPONENT_LUT = [0, 132, 396, 924, 1980, 4092, 8316, 16764]

    # Invert the bits of the input byte
    ulaw_byte = ~ulaw_byte & 0xFF

    # Extract the sign, exponent, and mantissa
    sign = ulaw_byte & 0x80  # Sign bit
    exponent = (ulaw_byte >> 4) & 0x07  # Exponent (3 bits)
    mantissa = ulaw_byte & 0x0F  # Mantissa (4 bits)

    # Calculate the linear PCM value
    sample = EXPONENT_LUT[exponent] + (mantissa << (exponent + 3))

    # Apply the sign
    if sign != 0:
        sample = -sample

    # Return the final 16-bit PCM value
    return sample & 0xFFFF


def ulaw_bytes_to_pcm16(ulaw_data):
    """Convert a sequence of µ-law encoded bytes to a list of 16-bit PCM values."""
    return np.array([ulaw2linear(byte) for byte in ulaw_data], dtype=np.int16)

# Function to process and decode the audio data
def process_audio_data(audio_data):
    if CODEC == "mulaw":
        pcm_data = ulaw_bytes_to_pcm16(audio_data)
        pcm_data = np.array(pcm_data, dtype=np.int16)
    elif CODEC == "pcm":
        audio_data = audio_data[:len(audio_data) - len(audio_data) % 2]
        pcm_data = np.frombuffer(audio_data, dtype=np.int16)
    return pcm_data

# Function to save PCM data as a WAV file
def save_as_wav(pcm_data, filename, sample_rate, channels, sample_width):
    with wave.open(filename, 'w') as wav_file:
        wav_file.setnchannels(channels)
        wav_file.setsampwidth(sample_width)
        wav_file.setframerate(sample_rate)
        wav_file.writeframes(pcm_data.tobytes())

# Provide the full directory path here
directory_path = '/Volumes/FRIEND/audio/'
output_wav_path = '/Volumes/FRIEND/output.wav'

# Read and join all PCM data
raw_audio_data = join_pcm_data(directory_path)

# Process and decode the audio data if necessary
pcm_data = process_audio_data(raw_audio_data)

# Save the joined PCM data as a WAV file
save_as_wav(pcm_data, output_wav_path, SAMPLE_RATE, CHANNELS, SAMPLE_WIDTH)

print(f"PCM data has been converted to WAV and saved as '{output_wav_path}'.")
