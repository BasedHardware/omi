import {useState, useEffect} from 'react';
import BleManager, {
  BleScanCallbackType,
  BleScanMatchMode,
  BleScanMode,
} from 'react-native-ble-manager';
import {NativeModules, NativeEventEmitter} from 'react-native';

const SECONDS_TO_SCAN_FOR = 3;
const SERVICE_UUIDS = ['19B10000-E8F2-537E-4F6C-D104768A1214'];
const serviceUUID = '19B10000-E8F2-537E-4F6C-D104768A1214';
const ALLOW_DUPLICATES = true;

const BleManagerModule = NativeModules.BleManager;
export const bleManagerEmitter = new NativeEventEmitter(BleManagerModule);

export const useBluetooth = navigation => {
  const [isScanning, setIsScanning] = useState(false);
  const [peripherals, setPeripherals] = useState(new Map());

  const startScan = () => {
    if (!isScanning) {
      // reset found peripherals before scan
      setPeripherals(new Map());

      try {
        console.debug('[startScan] starting scan...');
        setIsScanning(true);
        BleManager.scan(SERVICE_UUIDS, SECONDS_TO_SCAN_FOR, ALLOW_DUPLICATES, {
          matchMode: BleScanMatchMode.Sticky,
          scanMode: BleScanMode.LowLatency,
          callbackType: BleScanCallbackType.AllMatches,
        })
          .then(() => {
            console.debug('[startScan] scan promise returned successfully.');
          })
          .catch(err => {
            console.error('[startScan] ble scan returned in error', err);
          });
      } catch (error) {
        console.error('[startScan] ble scan error thrown', error);
      }
    }
  };

  const handleStopScan = () => {
    setIsScanning(false);
    console.debug('[handleStopScan] scan is stopped.');
  };

  const handleDisconnectedPeripheral = event => {
    console.debug(
      `[handleDisconnectedPeripheral][${event.peripheral}] disconnected.`,
    );
    setPeripherals(map => {
      let p = map.get(event.peripheral);
      if (p) {
        p.connected = false;
        return new Map(map.set(event.peripheral, p));
      }
      return map;
    });
  };

  const handleConnectPeripheral = event => {
    console.log(`[handleConnectPeripheral][${event.peripheral}] connected.`);
  };

  const handleDiscoverPeripheral = peripheral => {
    console.debug('[handleDiscoverPeripheral] new BLE peripheral=', peripheral);
    if (!peripheral.name) {
      peripheral.name = 'NO NAME';
    }
    if (
      peripheral.advertising &&
      peripheral.advertising.serviceUUIDs &&
      peripheral.advertising.serviceUUIDs.includes(serviceUUID)
    ) {
      console.debug(
        '[handleDiscoverPeripheral] Audio service found in peripheral:',
        peripheral.id,
      );
    }
    setPeripherals(map => {
      return new Map(map.set(peripheral.id, peripheral));
    });
  };

  const togglePeripheralConnection = async peripheral => {
    if (peripheral && peripheral.connected) {
      try {
        await BleManager.disconnect(peripheral.id);
      } catch (error) {
        console.error(
          `[togglePeripheralConnection][${peripheral.id}] error when trying to disconnect device.`,
          error,
        );
      }
    } else {
      await connectPeripheral(peripheral);
    }
  };

  const connectPeripheral = async peripheral => {
    try {
      if (peripheral) {
        setPeripherals(map => {
          let p = map.get(peripheral.id);
          if (p) {
            p.connecting = true;
            return new Map(map.set(p.id, p));
          }
          return map;
        });

        await BleManager.connect(peripheral.id);
        console.debug(`[connectPeripheral][${peripheral.id}] connected.`);
        await BleManager.retrieveServices(peripheral.id);
        console.debug(
          `[connectPeripheral][${peripheral.id}] Retrieved services.`,
        );

        setPeripherals(map => {
          let p = map.get(peripheral.id);
          if (p) {
            p.connecting = false;
            p.connected = true;
            return new Map(map.set(p.id, p));
          }
          return map;
        });

        // before retrieving services, it is often a good idea to let bonding & connection finish properly
        await sleep(900);

        /* Test read current RSSI value, retrieve services first */
        const peripheralData = await BleManager.retrieveServices(peripheral.id);
        console.debug(
          `[connectPeripheral][${peripheral.id}] retrieved peripheral services`,
          peripheralData,
        );

        setPeripherals(map => {
          let p = map.get(peripheral.id);
          if (p) {
            return new Map(map.set(p.id, p));
          }
          return map;
        });

        const rssi = await BleManager.readRSSI(peripheral.id);
        console.debug(
          `[connectPeripheral][${peripheral.id}] retrieved current RSSI value: ${rssi}.`,
        );

        if (peripheralData.characteristics) {
          for (let characteristic of peripheralData.characteristics) {
            if (characteristic.descriptors) {
              for (let descriptor of characteristic.descriptors) {
                try {
                  let data = await BleManager.readDescriptor(
                    peripheral.id,
                    characteristic.service,
                    characteristic.characteristic,
                    descriptor.uuid,
                  );
                  console.debug(
                    `[connectPeripheral][${peripheral.id}] ${characteristic.service} ${characteristic.characteristic} ${descriptor.uuid} descriptor read as:`,
                    data,
                  );
                } catch (error) {
                  console.error(
                    `[connectPeripheral][${peripheral.id}] failed to retrieve descriptor ${descriptor} for characteristic ${characteristic}:`,
                    error,
                  );
                }
              }
            }
          }
        }

        setPeripherals(map => {
          let p = map.get(peripheral.id);
          if (p) {
            p.rssi = rssi;
            return new Map(map.set(p.id, p));
          }
          return map;
        });
      }
    } catch (error) {
      console.error(
        `[connectPeripheral][${peripheral.id}] connectPeripheral error`,
        error,
      );
    }
  };

  function sleep(ms) {
    return new Promise(resolve => setTimeout(resolve, ms));
  }

  useEffect(() => {
    try {
      BleManager.start({showAlert: false})
        .then(() => console.debug('BleManager started.'))
        .catch(error =>
          console.error('BeManager could not be started.', error),
        );
    } catch (error) {
      console.error('unexpected error starting BleManager.', error);
      return;
    }

    const listeners = [
      bleManagerEmitter.addListener(
        'BleManagerDiscoverPeripheral',
        handleDiscoverPeripheral,
      ),
      bleManagerEmitter.addListener('BleManagerStopScan', handleStopScan),
      bleManagerEmitter.addListener(
        'BleManagerDisconnectPeripheral',
        handleDisconnectedPeripheral,
      ),
      bleManagerEmitter.addListener(
        'BleManagerConnectPeripheral',
        handleConnectPeripheral,
      ),
    ];

    handleAndroidPermissions();

    return () => {
      console.debug('[app] main component unmounting. Removing listeners...');
      for (const listener of listeners) {
        listener.remove();
      }
    };
  }, []);

  const handleAndroidPermissions = () => {
    if (Platform.OS === 'android' && Platform.Version >= 31) {
      PermissionsAndroid.requestMultiple([
        PermissionsAndroid.PERMISSIONS.BLUETOOTH_SCAN,
        PermissionsAndroid.PERMISSIONS.BLUETOOTH_CONNECT,
      ]).then(result => {
        if (result) {
          console.debug(
            '[handleAndroidPermissions] User accepts runtime permissions android 12+',
          );
        } else {
          console.error(
            '[handleAndroidPermissions] User refuses runtime permissions android 12+',
          );
        }
      });
    } else if (Platform.OS === 'android' && Platform.Version >= 23) {
      PermissionsAndroid.check(
        PermissionsAndroid.PERMISSIONS.ACCESS_FINE_LOCATION,
      ).then(checkResult => {
        if (checkResult) {
          console.debug(
            '[handleAndroidPermissions] runtime permission Android <12 already OK',
          );
        } else {
          PermissionsAndroid.request(
            PermissionsAndroid.PERMISSIONS.ACCESS_FINE_LOCATION,
          ).then(requestResult => {
            if (requestResult) {
              console.debug(
                '[handleAndroidPermissions] User accepts runtime permission android <12',
              );
            } else {
              console.error(
                '[handleAndroidPermissions] User refuses runtime permission android <12',
              );
            }
          });
        }
      });
    }
  };

  return {
    isScanning,
    peripherals,
    startScan,
    togglePeripheralConnection,
  };
};
