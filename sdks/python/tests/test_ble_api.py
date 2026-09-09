from omi.constants import PACKET_HEADER_BYTES
from omi import PACKET_HEADER_BYTES as P2


def test_packet_header_constant():
    assert PACKET_HEADER_BYTES == 3 == P2


def test_ble_module_importable_without_adapter():
    # Importing the module requires bleak installed in full env; constants path always works.
    from omi.constants import AUDIO_DATA_UUID, OMI_SERVICE_UUID

    assert AUDIO_DATA_UUID.startswith("19b10001")
    assert OMI_SERVICE_UUID.startswith("19b10000")


def test_scan_defaults_and_filtering():
    import asyncio
    from unittest.mock import AsyncMock, patch
    from omi.ble import scan, Device
    from omi.constants import OMI_SERVICE_UUID

    class MockBLEDevice:
        def __init__(self, address: str, name: str | None, rssi: int = -50):
            self.address = address
            self.name = name
            self.rssi = rssi

    fake_devices = [
        MockBLEDevice("11:22:33:44:55:66", "Omi Device", -45),
        MockBLEDevice("AA:BB:CC:DD:EE:FF", None, -70),
    ]

    # 1. Test default scan without service_uuids
    with patch("omi.ble.BleakScanner.discover", new_callable=AsyncMock) as mock_discover:
        mock_discover.return_value = fake_devices
        devices = asyncio.run(scan())
        mock_discover.assert_awaited_once_with(timeout=5.0)
        assert len(devices) == 2
        assert devices[0] == Device(id="11:22:33:44:55:66", name="Omi Device", rssi=-45)
        assert devices[1] == Device(id="AA:BB:CC:DD:EE:FF", name="", rssi=-70)

    # 2. Test scan with custom timeout
    with patch("omi.ble.BleakScanner.discover", new_callable=AsyncMock) as mock_discover:
        mock_discover.return_value = []
        devices = asyncio.run(scan(timeout=2.5))
        mock_discover.assert_awaited_once_with(timeout=2.5)
        assert devices == []

    # 3. Test scan with service_uuids list
    with patch("omi.ble.BleakScanner.discover", new_callable=AsyncMock) as mock_discover:
        mock_discover.return_value = [fake_devices[0]]
        devices = asyncio.run(scan(timeout=3.0, service_uuids=[OMI_SERVICE_UUID]))
        mock_discover.assert_awaited_once_with(timeout=3.0, service_uuids=[OMI_SERVICE_UUID])
        assert len(devices) == 1
        assert devices[0].id == "11:22:33:44:55:66"

    # 4. Test scan with sequence (tuple) of service_uuids
    with patch("omi.ble.BleakScanner.discover", new_callable=AsyncMock) as mock_discover:
        mock_discover.return_value = []
        asyncio.run(scan(service_uuids=(OMI_SERVICE_UUID, "custom-uuid")))
        mock_discover.assert_awaited_once_with(timeout=5.0, service_uuids=[OMI_SERVICE_UUID, "custom-uuid"])

    # 5. Test error propagation
    with patch("omi.ble.BleakScanner.discover", new_callable=AsyncMock) as mock_discover:
        mock_discover.side_effect = RuntimeError("Bluetooth adapter unavailable")
        import pytest
        with pytest.raises(RuntimeError, match="Bluetooth adapter unavailable"):
            asyncio.run(scan(service_uuids=[OMI_SERVICE_UUID]))

