from opuslib import Decoder

class OmiOpusDecoder:
    def __init__(self):
        self.decoder = Decoder(16000, 1)  # 16kHz mono

    def decode_packet(self, data):
        if len(data) <= 3:
            return b''

        # Remove 3-byte header
        clean_data = bytes(data[3:])

        # Decode Opus to PCM 16-bit
        try:
            pcm = self.decoder.decode(clean_data, 960, decode_fec=False)
            return pcm
        except Exception as e:
            print("Opus decode error:", e)
            return b''
