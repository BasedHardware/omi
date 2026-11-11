from omi.constants import PACKET_HEADER_BYTES
from omi import PACKET_HEADER_BYTES as P2


def test_packet_header_constant():
    assert PACKET_HEADER_BYTES == 3 == P2


def test_ble_module_importable_without_adapter():
    # Importing the module requires bleak installed in full env; constants path always works.
    from omi.constants import AUDIO_DATA_UUID, OMI_SERVICE_UUID

    assert AUDIO_DATA_UUID.startswith("19b10001")
    assert OMI_SERVICE_UUID.startswith("19b10000")
