import asyncio
import os
from omi.bluetooth import listen_to_omi
from omi.transcribe import transcribe
from omi.decoder import OmiOpusDecoder
from asyncio import Queue
import binascii  # Added for hex display of raw bytes
import sys
import struct  # For analyzing audio data
import time
import wave  # For saving audio files

OMI_MAC = "C1FF2F5C-3536-5AB0-9803-C1D5598EEA5E"
OMI_CHAR_UUID = "19B10001-E8F2-537E-4F6C-D104768A1214"

# Global flag to control verbose logging
VERBOSE_LOGGING = False

def main():
    api_key = os.getenv("DEEPGRAM_API_KEY")
    if not api_key:
        print("Set your Deepgram API Key in the DEEPGRAM_API_KEY environment variable.")
        return

    # Audio recording settings
    record_audio = True
    recording_seconds = 10  # Length of recording in seconds
    sample_rate = 16000
    channels = 1
    sample_width = 2  # 16-bit audio = 2 bytes per sample

    print("\n===== OMI SDK STARTED =====")
    print(f"Python version: {sys.version}")
    print(f"Deepgram API Key: {api_key[:5]}...{api_key[-5:]}")
    print(f"Target device MAC: {OMI_MAC}")
    print(f"BLE Characteristic: {OMI_CHAR_UUID}")
    if record_audio:
        print(f"🎙️ Recording {recording_seconds} seconds of audio to test.wav")
    print("===========================\n")

    audio_queue = Queue()
    decoder = OmiOpusDecoder()
    packet_counter = 0  # Counter for incoming packets
    audio_bytes_total = 0
    
    # For WAV recording
    recording_buffer = bytearray()
    recording_start_time = None
    
    # Add audio diagnostics
    last_audio_analysis = 0
    
    def analyze_audio_sample(pcm_data):
        """Analyze a sample of PCM data to check if it's valid audio."""
        if len(pcm_data) < 100:
            return
            
        # Convert to 16-bit signed integers
        samples = []
        for i in range(0, min(100, len(pcm_data)), 2):
            if i+1 < len(pcm_data):
                sample = struct.unpack("<h", pcm_data[i:i+2])[0]
                samples.append(sample)
        
        if not samples:
            return
            
        # Analyze audio characteristics
        max_val = max(samples)
        min_val = min(samples)
        avg = sum(samples) / len(samples)
        
        # Calculate zero crossings (rough frequency estimate)
        zero_crossings = 0
        for i in range(1, len(samples)):
            if (samples[i-1] < 0 and samples[i] >= 0) or (samples[i-1] >= 0 and samples[i] < 0):
                zero_crossings += 1
                
        print(f"\n📊 Audio Analysis: Min={min_val}, Max={max_val}, Avg={avg:.1f}, ZeroCross={zero_crossings}")
        
        # Check for potential issues
        if max_val < 100 and min_val > -100:
            print("⚠️ Warning: Audio levels very low - might be too quiet for transcription")
        if zero_crossings < 5:
            print("⚠️ Warning: Few zero crossings - might be DC offset or non-speech audio")
        
        # Show a mini waveform visualization
        print("📈 Waveform: ", end="")
        scale = 40 / (max(abs(max_val), abs(min_val)) + 1)  # Scale to fit in terminal
        for i in range(0, min(40, len(samples)), 2):
            height = int(samples[i] * scale)
            if height > 0:
                print("▁▂▃▄▅▆▇█"[min(7, height//5)], end="")
            elif height < 0:
                print("▁▂▃▄▅▆▇█"[min(7, abs(height)//5)], end="")
            else:
                print("▁", end="")
        print()

    def save_wav_file(audio_data, filename="test.wav"):
        """Save audio data as a WAV file."""
        with wave.open(filename, 'wb') as wav_file:
            wav_file.setnchannels(channels)
            wav_file.setsampwidth(sample_width)
            wav_file.setframerate(sample_rate)
            wav_file.writeframes(audio_data)
        print(f"\n✅ Audio saved to {filename} ({len(audio_data)/sample_rate/sample_width:.2f} seconds)")
        
        # Also save a version with higher volume for testing
        amplified_data = bytearray()
        for i in range(0, len(audio_data), 2):
            if i+1 < len(audio_data):
                sample = struct.unpack("<h", audio_data[i:i+2])[0]
                # Amplify by factor of 5
                amplified_sample = max(min(sample * 5, 32767), -32768)  # Clamp to 16-bit range
                amplified_data.extend(struct.pack("<h", int(amplified_sample)))
                
        amplified_filename = "test_amplified.wav"
        with wave.open(amplified_filename, 'wb') as wav_file:
            wav_file.setnchannels(channels)
            wav_file.setsampwidth(sample_width)
            wav_file.setframerate(sample_rate)
            wav_file.writeframes(amplified_data)
        print(f"✅ Amplified audio saved to {amplified_filename}")

    def handle_ble_data(sender, data):
        nonlocal packet_counter, audio_bytes_total, last_audio_analysis
        nonlocal recording_buffer, recording_start_time, record_audio
        
        packet_counter += 1
        
        # Concise logging of packet data (single line)
        seq = data[0] if len(data) > 0 else 0
        
        # Process audio data
        decoded_pcm = decoder.decode_packet(data)
        if decoded_pcm:
            audio_bytes_total += len(decoded_pcm)
            
            # Recording logic
            if record_audio:
                # Start recording timer on first packet
                if recording_start_time is None:
                    recording_start_time = time.time()
                    print("🎙️ Started recording audio...")
                
                # Add to recording buffer
                recording_buffer.extend(decoded_pcm)
                
                # Check if we've recorded enough
                elapsed = time.time() - recording_start_time
                if elapsed >= recording_seconds:
                    if record_audio:  # Check again to avoid race condition
                        save_wav_file(recording_buffer)
                        # Disable further recording
                        record_audio = False
            
            # Super concise logging
            if packet_counter % 20 == 0:
                print(f"Packet #{packet_counter} | Seq:{seq} | {len(data)}B → {len(decoded_pcm)}B PCM | Total: {audio_bytes_total} bytes")
            
            # Analyze audio periodically
            current_time = time.time()
            if current_time - last_audio_analysis > 10:  # Every 10 seconds
                analyze_audio_sample(decoded_pcm)
                last_audio_analysis = current_time
            
            try:
                audio_queue.put_nowait(decoded_pcm)
            except Exception as e:
                print(f"Queue Error: {e}")
        else:
            print(f"Decode failed: Packet #{packet_counter} | Seq:{seq} | {len(data)}B raw data")

    async def run():
        print("Starting OMI Bluetooth listener...")
        print(f"Connecting to OMI device with MAC: {OMI_MAC}")
        await asyncio.gather(
            listen_to_omi(OMI_MAC, OMI_CHAR_UUID, handle_ble_data),
            transcribe(audio_queue, api_key)
        )

    try:
        asyncio.run(run())
    except KeyboardInterrupt:
        print("\nApplication terminated by user")
        # Save any recorded audio on exit
        if record_audio and len(recording_buffer) > 0:
            save_wav_file(recording_buffer)
    except Exception as e:
        print(f"Application error: {e}")

if __name__ == '__main__':
    main()
