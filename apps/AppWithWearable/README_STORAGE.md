# Code Changes Documentation

## File: `gatt_utils.dart`

### Summary of Changes

- **Added New Constants:**
  - `storageServiceUuid`: Added a new UUID for the storage service.
  - `filesInStorageNotifyCharacteristicUuid`: Added a new UUID for the characteristic to notify about files in storage.
  - `storageModeSelectorCharacteristicUuid`: Added a new UUID for the characteristic to select the storage mode.

# Code Updates

## 2. Added Storage Service & Characteristics

### New Methods Added

#### getFilesInStorageListener

- **Description:** Listens for changes in the number of files in storage.
- **Callback Parameter:** `void Function(int)? onFilesInStorageChange`
- **Characteristic UUID:** `filesInStorageNotifyCharacteristicUuid`

#### setStorageMode

- **Description:** Sets the storage mode on the device.
- **Parameter:** `int mode` (the mode to be set)
- **Characteristic UUID:** `storageModeSelectorCharacteristicUuid`
- **Details:** Converts the integer mode to 4 bytes using `ByteData` and writes it to the characteristic.

