# Changelog

All notable changes to this project will be documented in this file.

## [1.4.3] 2024-11-27

### Fixed
 - BT5 examples for non-esp devices.
 - Build errors when configured as a non-connecting device

### Added
 - Coded PHY support for nRF52833 and nRF52820

## [1.4.2] 2024-06-17

### Fixed
 - `CONFIG_BT_NIMBLE_NVS_PERSIST` value not being used to enable/disable persistance.
 - Set service handle in `NimBLEService::getHandle` function if not set already.
 - NimBLE_service_data_advertiser example updated to initialize the advertising pointer after stack initialization.
 - Unhandled exception on `NimBLECharacteristic::handleGapEvent` when the connection handle is invalid.
 - `NimBLEHIDDevice::pnp` now correctly sets the byte order.
 - `NimBLEEddystoneTLM` now correctly sets/gets negative temperatures.
 - Adding to the whitelist will now allow the device to be added again if the previous attempts failed.
 - The IPC calls added to esp_nimble_hci have been removed to prevent IPC stack crashing.
 - Espressif log tag renamed from "TAG" to "LOG_TAG" to avoid conflict with Arduino core definition.
 - Removed broken links in docs

### Added
 - `NimBLEAdvertisedDevice` new method: `getAdvFlags`, to read the flags advertised.
 - `NimBLEAdvertising::setManufacturerData` new overload method that accepts a vector of `uint8_t`.
 - `NimBLEAdvertisementData::setManufacturerData` new overload method that accepts a vector of `uint8_t`.
 - `NimBLEAdvertisedDevice` new method: `getPayloadByType`, to get data from generic data types advertised.
 - `NimBLEService` new method: `isStarted`, checks if the service has been started.
 - `NimBLEAdvertising` new method: `removeServices` removes all service UUID's from the advertisement.
 - `NimBLEAdvertisementData` new method: `clearData` sets all data to NULL to reuse the instance.

### Changed
 - `NimBLEAdvertisedDevice::getManufacturerData`, now takes an index value parameter to use when there is more than 1 instance of manufacturer data.
 - `NimBLEAdvertising` directed peer address parameter to advertising start.
 - Update NimBLE core to esp-nimble @0fc6282
 - Can now create more than 255 Characteristics/Descriptors in a service.
 - `nimble_port_freertos_get_hs_hwm` function is now available to the application to get the core task stack usage.
 - changed default pairing keys shared to include ID key which is now needed by iOS
 - Removed abort in server start when a service is not found, logs a warning message instead.
 - `NimBLEAdvertising::start` on complete callback is now a std::function to allow the use of std::bind to class methods
 - `NimBLEAdvertising` setXXX methods will now properly clear the previous data before setting the new values.
 - Removed asserts in `NimBLECharacteristic` event handler when conn_handle is invalid, sends a NULL conn info to the callback instead.

## [1.4.1] - 2022-10-23

### Fixed
 - Compile warning removed for esp32c3
 - NimBLEDevice::getPower incorrect value when power level is -3db.
 - Failed pairing when already in progress.

### Changed
 - Revert previous change that forced writing with response when subscribing in favor of allowing the application to decide.

### Added
 - Added NimBLEHIDDevice::batteryLevel.
 - Added NimBLEDevice::setDeviceName allowing for changing the device name while the BLE stack is active.
 - CI build tests.
 - Missing items in CHANGELOG that were not recorded correctly

## [1.4.0] - 2022-07-10

### Fixed
- Fixed missing data from long notification values.
- Fixed NimbleCharacteristicCallbacks::onRead not being called when a non-long read command is received.

### Changed
- Updated NimBLE core to use the v1.4.0 branch of esp-nimble.
- AD flags are no longer set in the advertisements of non-connectable beacons, freeing up 3 bytes of advertisement room.
- Config option CONFIG_BT_NIMBLE_DEBUG replaced with CONFIG_BT_NIMBLE_LOG_LEVEL (see src/nimconfig.h for usage)
- Config option CONFIG_NIMBLE_CPP_ENABLE_ADVERTISMENT_TYPE_TEXT renamed to CONFIG_NIMBLE_CPP_ENABLE_ADVERTISEMENT_TYPE_TEXT
- Config option CONFIG_BT_NIMBLE_TASK_STACK_SIZE renamed to CONFIG_BT_NIMBLE_HOST_TASK_STACK_SIZE

### Added
- Preliminary support for non-esp devices, NRF51 and NRF52 devices supported with [n-able arduino core](https://github.com/h2zero/n-able-Arduino)
- Alias added for  `NimBLEServerCallbacks::onMTUChange` to `onMtuChanged` in order to support porting code from original library.
- `NimBLEAttValue` Class added to reduce and control RAM footprint of characteristic/descriptor values and support conversions from Arduino Strings and many other data types.
- Bluetooth 5 extended advertising support for capable devices. CODED Phy, 2M Phy, extended advertising data, and multi-advertising are supported, periodic advertising will be implemented in the future.

## [1.3.8] - 2022-04-27

### Fixed
- Fix compile error with ESP32S3.
- Prevent a potential crash when retrieving characteristics from a service if the result was successful but no characteristics found.

### Changed
- Save resources when retrieving descriptors if the characteristic handle is the same as the end handle (no descriptors).
- Subscribing to characteristic notifications/indications will now always use write with response, as per BLE specifications.
- `NimBLEClient::discoverAttributes` now returns a bool value to indicate success/failure

## [1.3.7] - 2022-02-15

### Fixed

- Crash when retrieving an attribute that does not exist on the peer.
- Memory leak when deleting client instances.
- Compilation errors for esp32s3

## [1.3.6] - 2022-01-18

### Changed
- When retrieving attributes from a server fails with a 128bit UUID containing the ble base UUID another attempt will be made with the 16bit version of the UUID.

### Fixed
- Memory leak when services are changed on server devices.
- Rare crashing that occurs when BLE commands are sent from ISR context using IPC.
- Crashing caused by uninitialized disconnect timer in client.
- Potential crash due to uninitialized advertising callback pointer.

## [1.3.5] - 2022-01-14

### Added
- CONFIG_NIMBLE_CPP_DEBUG_LEVEL macro in nimconfig.h to allow setting the log level separately from the Arduino core log level.

### Fixed
- Memory leak when initializing/deinitializing the BLE stack caused by new FreeRTOS timers be created on each initialization.

## [1.3.4] - 2022-01-09

### Fixed
- Workaround for latest Arduino-esp32 core that causes tasks not to block when required, which caused functions to return prematurely resulting in exceptions/crashing.
- The wrong length value was being used to set the values read from peer attributes. This has been corrected to use the proper value size.

## [1.3.3] - 2021-11-24

### Fixed
- Workaround added for FreeRTOS bug that affected timers, causing scan and advertising timer expirations to not correctly trigger callbacks.

## [1.3.2] - 2021-11-20

### Fixed
- Added missing macros for scan filter.

### Added
- `NimBLEClient::getLastError` : Gets the error code of the last function call that produces a return code from the stack.

## [1.3.1] - 2021-08-04

### Fixed
- Corrected a compiler/linker error when an application or a library uses bluetooth classic due to the redefinition of `btInUse`.

## [1.3.0] - 2021-08-02

### Added
- `NimBLECharacteristic::removeDescriptor`: Dynamically remove a descriptor from a characteristic. Takes effect after all connections are closed and sends a service changed indication.
- `NimBLEService::removeCharacteristic`: Dynamically remove a characteristic from a service. Takes effect after all connections are closed and sends a service changed indication
- `NimBLEServerCallbacks::onMTUChange`: This is callback is called when the MTU is updated after connection with a client.
- ESP32C3 support

- Whitelist API:
  - `NimBLEDevice::whiteListAdd`: Add a device to the whitelist.
  - `NimBLEDevice::whiteListRemove`: Remove a device from the whitelist.
  - `NimBLEDevice::onWhiteList`: Check if the device is on the whitelist.
  - `NimBLEDevice::getWhiteListCount`: Gets the size of the whitelist
  - `NimBLEDevice::getWhiteListAddress`: Get the address of a device on the whitelist by index value.

- Bond management API:
  - `NimBLEDevice::getNumBonds`: Gets the number of bonds stored.
  - `NimBLEDevice::isBonded`: Checks if the device is bonded.
  - `NimBLEDevice::deleteAllBonds`: Deletes all bonds.
  - `NimBLEDevice::getBondedAddress`: Gets the address of a bonded device by the index value.

- `NimBLECharacteristic::getCallbacks` to retrieve the current callback handler.
- Connection Information class: `NimBLEConnInfo`.
- `NimBLEScan::clearDuplicateCache`: This can be used to reset the cache of advertised devices so they will be immediately discovered again.

### Changed
- FreeRTOS files have been removed as they are not used by the library.
- Services, characteristics and descriptors can now be created statically and added after.
- Excess logging and some asserts removed.
- Use ESP_LOGx macros to enable using local log level filtering.

### Fixed
- `NimBLECharacteristicCallbacks::onSubscribe` Is now called after the connection is added to the vector.
- Corrected bonding failure when reinitializing the BLE stack.
- Writing to a characteristic with a std::string value now correctly writes values with null characters.
- Retrieving remote descriptors now uses the characteristic end handle correctly.
- Missing data in long writes to remote descriptors.
- Hanging on task notification when sending an indication from the characteristic callback.
- BLE controller memory could be released when using Arduino as a component.
- Compile errors with NimBLE release 1.3.0.

## [1.2.0] - 2021-02-08

### Added
- `NimBLECharacteristic::getDescriptorByHandle`: Return the BLE Descriptor for the given handle.

- `NimBLEDescriptor::getStringValue`: Get the value of this descriptor as a string.

- `NimBLEServer::getServiceByHandle`: Get a service by its handle.

- `NimBLEService::getCharacteristicByHandle`: Get a pointer to the characteristic object with the specified handle.

- `NimBLEService::getCharacteristics`: Get the vector containing pointers to each characteristic associated with this service.
Overloads to get a vector containing pointers to all the characteristics in a service with the UUID. (supports multiple same UUID's in a service)
  - `NimBLEService::getCharacteristics(const char *uuid)`
  - `NimBLEService::getCharacteristics(const NimBLEUUID &uuid)`

- `NimBLEAdvertisementData` New methods:
  - `NimBLEAdvertisementData::addTxPower`: Adds transmission power to the advertisement.
  - `NimBLEAdvertisementData::setPreferredParams`: Adds connection parameters to the advertisement.
  - `NimBLEAdvertisementData::setURI`: Adds URI data to the advertisement.

- `NimBLEAdvertising` New methods:
  - `NimBLEAdvertising::setName`: Set the name advertised.
  - `NimBLEAdvertising::setManufacturerData`: Adds manufacturer data to the advertisement.
  - `NimBLEAdvertising::setURI`: Adds URI data to the advertisement.
  - `NimBLEAdvertising::setServiceData`: Adds service data to the advertisement.
  - `NimBLEAdvertising::addTxPower`: Adds transmission power to the advertisement.
  - `NimBLEAdvertising::reset`: Stops the current advertising and resets the advertising data to the default values.

- `NimBLEDevice::setScanFilterMode`: Set the controller duplicate filter mode for filtering scanned devices.

- `NimBLEDevice::setScanDuplicateCacheSize`: Sets the number of advertisements filtered before the cache is reset.

- `NimBLEScan::setMaxResults`:  This allows for setting a maximum number of advertised devices stored in the results vector.

- `NimBLEAdvertisedDevice` New data retrieval methods added:
  - `haveAdvInterval/getAdvInterval`: checks if the interval is advertised / gets the advertisement interval value.

  - `haveConnParams/getMinInterval/getMaxInterval`: checks if the parameters are advertised / get min value / get max value.

  - `haveURI/getURI`: checks if a URI is advertised / gets the URI data.

  - `haveTargetAddress/getTargetAddressCount/getTargetAddress(index)`: checks if a target address is present / gets a count of the addresses targeted / gets the address of the target at index.

### Changed
- `nimconfig.h` (Arduino) is now easier to use.

- `NimBLEServer::getServiceByUUID` Now takes an extra parameter of instanceID to support multiple services with the same UUID.

- `NimBLEService::getCharacteristic` Now takes an extra parameter of instanceID to support multiple characteristics with the same UUID.

- `NimBLEAdvertising` Transmission power is no longer advertised by default and can be added to the advertisement by calling `NimBLEAdvertising::addTxPower`

- `NimBLEAdvertising` Custom scan response data can now be used without custom advertisement.

- `NimBLEScan` Now uses the controller duplicate filter.

- `NimBLEAdvertisedDevice` Has been refactored to store the complete advertisement payload and no longer parses the data from each advertisement.
Instead the data will be parsed on-demand when the user application asks for specific data.

### Fixed
- `NimBLEHIDDevice` Characteristics now use encryption, this resolves an issue with communicating with devices requiring encryption for HID devices.


## [1.1.0] - 2021-01-20

### Added
- `NimBLEDevice::setOwnAddrType` added to enable the use of random and random-resolvable addresses, by asukiaaa

- New examples for securing and authenticating client/server connections, by mblasee.

- `NimBLEAdvertising::SetMinPreferred` and `NimBLEAdvertising::SetMinPreferred` re-added.

- Conditional checks added for command line config options in `nimconfig.h` to support custom configuration in platformio.

- `NimBLEClient::setValue` Now takes an extra bool parameter `response` to enable the use of write with response (default = false).

- `NimBLEClient::getCharacteristic(uint16_t handle)` Enabling the use of the characteristic handle to be used to find
the NimBLERemoteCharacteristic object.

- `NimBLEHIDDevice` class added by wakwak-koba.

- `NimBLEServerCallbacks::onDisconnect` overloaded callback added to provide a ble_gap_conn_desc parameter for the application
to obtain information about the disconnected client.

- Conditional checks in `nimconfig.h` for command line defined macros to support platformio config settings.

### Changed
- `NimBLEAdvertising::start` now returns a bool value to indicate success/failure.

- Some asserts were removed in `NimBLEAdvertising::start` and replaced with better return code handling and logging.

- If a host reset event occurs, scanning and advertising will now only be restarted if their previous duration was indefinite.

- `NimBLERemoteCharacteristic::subscribe` and `NimBLERemoteCharacteristic::registerForNotify` will now set the callback
regardless of the existence of the CCCD and return true unless the descriptor write operation failed.

- Advertising tx power level is now sent in the advertisement packet instead of scan response.

- `NimBLEScan` When the scan ends the scan stopped flag is now set before calling the scan complete callback (if used)
this allows the starting of a new scan from the callback function.

### Fixed
- Sometimes `NimBLEClient::connect` would hang on the task block if no event arrived to unblock.
A time limit has been added to timeout appropriately.

- When getting descriptors for a characteristic the end handle of the service was used as a proxy for the characteristic end
handle. This would be rejected by some devices and has been changed to use the next characteristic handle as the end when possible.

- An exception could occur when deleting a client instance if a notification arrived while the attribute vectors were being
deleted. A flag has been added to prevent this.

- An exception could occur after a host reset event when the host re-synced if the tasks that were stopped during the event did
not finish processing. A yield has been added after re-syncing to allow tasks to finish before proceeding.

- Occasionally the controller would fail to send a disconnected event causing the client to indicate it is connected
and would be unable to reconnect. A timer has been added to reset the host/controller if it expires.

- Occasionally the call to start scanning would get stuck in a loop on BLE_HS_EBUSY, this loop has been removed.

- 16bit and 32bit UUID's in some cases were not discovered or compared correctly if the device
advertised them as 16/32bit but resolved them to 128bits. Both are now checked.

- `FreeRTOS` compile errors resolved in latest Arduino core and IDF v3.3.

- Multiple instances of `time()` called inside critical sections caused sporadic crashes, these have been moved out of critical regions.

- Advertisement type now correctly set when using non-connectable (advertiser only) mode.

- Advertising payload length correction, now accounts for appearance.

- (Arduino) Ensure controller mode is set to BLE Only.


## [1.0.2] - 2020-09-13

### Changed

- `NimBLEAdvertising::start` Now takes 2 optional parameters, the first is the duration to advertise for (in seconds), the second is a
callback that is invoked when advertising ends and takes a pointer to a `NimBLEAdvertising` object (similar to the `NimBLEScan::start` API).

- (Arduino) Maximum BLE connections can now be altered by only changing the value of `CONFIG_BT_NIMBLE_MAX_CONNECTIONS` in `nimconfig.h`.
Any changes to the controller max connection settings in `sdkconfig.h` will now have no effect when using this library.

- (Arduino) Revert the previous change to fix the advertising start delay. Instead a replacement fix that routes all BLE controller commands from
a task running on core 0 (same as the controller) has been implemented. This improves response times and reliability for all BLE functions.


## [1.0.1] - 2020-09-02

### Added

- Empty `NimBLEAddress` constructor: `NimBLEAddress()` produces an address of 00:00:00:00:00:00 type 0.
- Documentation of the difference of NimBLEAddress::getNative vs the original bluedroid library.

### Changed

- notify_callback typedef is now defined as std::function to enable the use of std::bind to call a class member function.

### Fixed

- Fix advertising start delay when first called.


## [1.0.0] - 2020-08-22

First stable release.

All the original library functionality is complete and many extras added with full documentation.
