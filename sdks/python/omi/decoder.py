from typing import Union
from opuslib import Decoder

class OmiOpusDecoder:
    """Opus audio decoder for Omi device audio packets."""
    
    def __init__(self) -> None:
        """Initialize decoder for 16kHz mono audio."""
        self.decoder = Decoder(16000, 1)  # 16kHz mono

    def decode_packet(self, data: Union[bytes, bytearray]) -> bytes:
        """
        Decode Opus-encoded audio packet to PCM.
        
        Args:
            data: Raw audio packet from Omi device (includes 3-byte header)
            
        Returns:
            PCM audio data as bytes, or empty bytes if decode fails
        """
        if len(data) <= 3:
            return b''

        # Remove 3-byte header
        clean_data = bytes(data[3:])

        # Decode Opus to PCM 16-bit
        try:
            pcm: bytes = self.decoder.decode(clean_data, 960, decode_fec=False)
            return pcm
        except Exception as e:
            print("Opus decode error:", e)
            return b''
