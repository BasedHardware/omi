from omi.constants import AUDIO_DATA_UUID, PACKET_HEADER_BYTES, PCM_SAMPLE_RATE_HZ
from omi.decoder import OmiOpusDecoder


def test_constants():
    assert AUDIO_DATA_UUID.startswith("19b10001")
    assert PACKET_HEADER_BYTES == 3
    assert PCM_SAMPLE_RATE_HZ == 16000


def test_decoder_short_packet():
    dec = OmiOpusDecoder.__new__(OmiOpusDecoder)
    # avoid constructing real opus decoder
    class Dummy:
        def decode(self, *a, **k):
            raise AssertionError("should not decode short packet")

    dec.decoder = Dummy()
    assert OmiOpusDecoder.decode_packet(dec, b"\x00\x01") == b""
