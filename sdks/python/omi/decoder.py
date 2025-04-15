from opuslib import Decoder
import struct
import numpy as np

class OmiOpusDecoder:
    def __init__(self):
        self.decoder = Decoder(16000, 1)  # 16kHz mono
        self.packet_counter = 0
        self.total_pcm_bytes = 0
        self.warnings_count = 0
        
    def decode_packet(self, data):
        self.packet_counter += 1
        
        if len(data) <= 3:
            # Only log every 20th warning to reduce noise
            self.warnings_count += 1
            if self.warnings_count % 20 == 0:
                print(f"Warning: Received {self.warnings_count} packets that were too short")
            return b''
            
        # Skip verbose header logging
        
        # Remove 3-byte header
        clean_data = bytes(data[3:])

        # Decode Opus to PCM 16-bit
        try:
            pcm = self.decoder.decode(clean_data, 960, decode_fec=False)
            
            # Validate PCM data
            if len(pcm) == 0:
                return b''
                
            # Ensure we have proper 16-bit PCM audio (check against unexpected formats)
            if len(pcm) % 2 != 0:
                # Pad with zero byte if necessary
                pcm += b'\x00'
            
            # Convert bytes to numpy array of 16-bit integers for processing
            samples = np.frombuffer(pcm, dtype=np.int16)
            
            # Fix DC offset (center the audio around zero)
            if len(samples) > 0:
                dc_offset = np.mean(samples)
                if abs(dc_offset) > 100:  # Only correct if there's significant DC offset
                    samples = samples - int(dc_offset)
                
                # Normalize audio volume if it's too quiet
                max_amplitude = max(np.max(samples), abs(np.min(samples)))
                if max_amplitude < 3000:  # Boost if below reasonable level
                    gain_factor = min(5.0, 8000 / max(max_amplitude, 1))  # Cap at 5x gain
                    samples = (samples * gain_factor).astype(np.int16)
            
            # Convert back to bytes
            processed_pcm = samples.tobytes()
            
            self.total_pcm_bytes += len(processed_pcm)
            
            # Check audio levels but log only serious issues
            if len(processed_pcm) >= 10:
                # Convert first few samples to 16-bit integers for level debugging
                samples = struct.unpack("<5h", processed_pcm[:10])
                min_val = min(samples)
                max_val = max(samples)
                
                # Audio level warning for extremely quiet audio - log only occasionally
                if max_val < 30 and min_val > -30 and self.packet_counter % 100 == 0:
                    print(f"Warning: Very low audio levels detected (min={min_val}, max={max_val})")
            
            return processed_pcm
            
        except Exception as e:
            # Log errors but not too frequently
            if self.packet_counter % 20 == 0 or "frame length too small" in str(e):
                print(f"Opus decode error: {e}")
            return b''
