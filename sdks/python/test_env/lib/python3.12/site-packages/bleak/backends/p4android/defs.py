# -*- coding: utf-8 -*-

import enum

from jnius import autoclass, cast

import bleak.exc
from bleak.uuids import normalize_uuid_16

# caching constants avoids unnecessary extra use of the jni-python interface, which can be slow

List = autoclass("java.util.ArrayList")
UUID = autoclass("java.util.UUID")
BluetoothAdapter = autoclass("android.bluetooth.BluetoothAdapter")
ScanCallback = autoclass("android.bluetooth.le.ScanCallback")
ScanFilter = autoclass("android.bluetooth.le.ScanFilter")
ScanFilterBuilder = autoclass("android.bluetooth.le.ScanFilter$Builder")
ScanSettings = autoclass("android.bluetooth.le.ScanSettings")
ScanSettingsBuilder = autoclass("android.bluetooth.le.ScanSettings$Builder")
BluetoothDevice = autoclass("android.bluetooth.BluetoothDevice")
BluetoothGatt = autoclass("android.bluetooth.BluetoothGatt")
BluetoothGattCharacteristic = autoclass("android.bluetooth.BluetoothGattCharacteristic")
BluetoothGattDescriptor = autoclass("android.bluetooth.BluetoothGattDescriptor")
BluetoothProfile = autoclass("android.bluetooth.BluetoothProfile")

PythonActivity = autoclass("org.kivy.android.PythonActivity")
ParcelUuid = autoclass("android.os.ParcelUuid")
activity = cast("android.app.Activity", PythonActivity.mActivity)
context = cast("android.content.Context", activity.getApplicationContext())

ScanResult = autoclass("android.bluetooth.le.ScanResult")

BLEAK_JNI_NAMESPACE = "com.github.hbldh.bleak"
PythonScanCallback = autoclass(BLEAK_JNI_NAMESPACE + ".PythonScanCallback")
PythonBluetoothGattCallback = autoclass(
    BLEAK_JNI_NAMESPACE + ".PythonBluetoothGattCallback"
)


class ScanFailed(enum.IntEnum):
    ALREADY_STARTED = ScanCallback.SCAN_FAILED_ALREADY_STARTED
    APPLICATION_REGISTRATION_FAILED = (
        ScanCallback.SCAN_FAILED_APPLICATION_REGISTRATION_FAILED
    )
    FEATURE_UNSUPPORTED = ScanCallback.SCAN_FAILED_FEATURE_UNSUPPORTED
    INTERNAL_ERROR = ScanCallback.SCAN_FAILED_INTERNAL_ERROR


GATT_SUCCESS = 0x0000
# TODO: we may need different lookups, e.g. one for bleak.exc.CONTROLLER_ERROR_CODES
GATT_STATUS_STRINGS = {
    # https://developer.android.com/reference/android/bluetooth/BluetoothGatt
    # https://android.googlesource.com/platform/external/bluetooth/bluedroid/+/5738f83aeb59361a0a2eda2460113f6dc9194271/stack/include/gatt_api.h
    # https://android.googlesource.com/platform/system/bt/+/master/stack/include/gatt_api.h
    # https://www.bluetooth.com/specifications/bluetooth-core-specification/
    **bleak.exc.PROTOCOL_ERROR_CODES,
    0x007F: "Too Short",
    0x0080: "No Resources",
    0x0081: "Internal Error",
    0x0082: "Wrong State",
    0x0083: "DB Full",
    0x0084: "Busy",
    0x0085: "Error",
    0x0086: "Command Started",
    0x0087: "Illegal Parameter",
    0x0088: "Pending",
    0x0089: "Auth Failure",
    0x008A: "More",
    0x008B: "Invalid Configuration",
    0x008C: "Service Started",
    0x008D: "Encrypted No MITM",
    0x008E: "Not Encrypted",
    0x008F: "Congested",
    0x0090: "Duplicate Reg",
    0x0091: "Already Open",
    0x0092: "Cancel",
    0x0101: "Failure",
}

CHARACTERISTIC_PROPERTY_DBUS_NAMES = {
    BluetoothGattCharacteristic.PROPERTY_BROADCAST: "broadcast",
    BluetoothGattCharacteristic.PROPERTY_EXTENDED_PROPS: "extended-properties",
    BluetoothGattCharacteristic.PROPERTY_INDICATE: "indicate",
    BluetoothGattCharacteristic.PROPERTY_NOTIFY: "notify",
    BluetoothGattCharacteristic.PROPERTY_READ: "read",
    BluetoothGattCharacteristic.PROPERTY_SIGNED_WRITE: "authenticated-signed-writes",
    BluetoothGattCharacteristic.PROPERTY_WRITE: "write",
    BluetoothGattCharacteristic.PROPERTY_WRITE_NO_RESPONSE: "write-without-response",
}

CLIENT_CHARACTERISTIC_CONFIGURATION_UUID = normalize_uuid_16(0x2902)
