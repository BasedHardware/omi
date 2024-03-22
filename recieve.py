import serial
import wave
import struct

# Serial port configuration
serial_port = '/dev/ttyUSB0'  # Change this to your serial port
baud_rate = 9600

# WAV file configuration
wav_filename = 'output.wav'
audio_channels = 1
sample_width = 2  # 2 bytes for 16-bit samples
frame_rate = 16000  # Same as your Arduino's sample rate
record_seconds = 5  # Duration of recording

# Open serial port
ser = serial.Serial(serial_port, baud_rate)

# Open a WAV file for writing
wav_file = wave.open(wav_filename, 'w')
wav_file.setnchannels(audio_channels)
wav_file.setsampwidth(sample_width)
wav_file.setframerate(frame_rate)

print("Recording...")

# Read data from serial and write to WAV file
try:
    bytes_to_read = frame_rate * sample_width * audio_channels * record_seconds
    data = ser.read(bytes_to_read)
    
    # Assuming the Arduino is sending little-endian data; adjust if necessary
    for i in range(0, len(data), sample_width):
        sample = struct.unpack('<h', data[i:i+sample_width])[0]
        wav_file.writeframesraw(struct.pack('<h', sample))

finally:
    # Clean up
    ser.close()
    wav_file.close()

print("Recording finished. WAV file is saved.")
