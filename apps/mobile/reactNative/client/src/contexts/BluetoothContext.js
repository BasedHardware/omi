import React, {createContext, useContext, useState, useEffect} from 'react';
import BleManager, {
  BleScanCallbackType,
  BleScanMatchMode,
  BleScanMode,
} from 'react-native-ble-manager';
import {
  NativeModules,
  NativeEventEmitter,
  PermissionsAndroid,
  Platform,
} from 'react-native';

export const BluetoothContext = createContext();

const SECONDS_TO_SCAN_FOR = 3;
const SERVICE_UUIDS = ['19B10000-E8F2-537E-4F6C-D104768A1214'];
const serviceUUID = '19B10000-E8F2-537E-4F6C-D104768A1214';
const ALLOW_DUPLICATES = true;

const BleManagerModule = NativeModules.BleManager;
const bleManagerEmitter = new NativeEventEmitter(BleManagerModule);

export const BluetoothProvider = ({children}) => {
  const [isScanning, setIsScanning] = useState(false);
  const [peripherals, setPeripherals] = useState(new Map());

  const startScan = () => {
    if (!isScanning) {
      setPeripherals(new Map());
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
          setIsScanning(false);
        });
    }
  };

  useEffect(() => {
    // Permissions then start BleManager
    handleAndroidPermissions();
    // Initialize BleManager
    BleManager.start({showAlert: false})
      .then(() => {
        console.debug('BleManager started.');

        // Set up listeners
        const listeners = [
          bleManagerEmitter.addListener(
            'BleManagerDiscoverPeripheral',
            handleDiscoverPeripheral,
          ),
          bleManagerEmitter.addListener('BleManagerStopScan', () =>
            setIsScanning(false),
          ),
          bleManagerEmitter.addListener(
            'BleManagerDisconnectPeripheral',
            handleDisconnectedPeripheral,
          ),
          bleManagerEmitter.addListener(
            'BleManagerConnectPeripheral',
            handleConnectPeripheral,
          ),
        ];

        //
        setTimeout(() => {
          startScan();
        }, 1000);

        // Clean up on component unmount
        return () => {
          console.debug(
            '[BluetoothProvider] Unmounting. Removing listeners...',
          );
          listeners.forEach(listener => listener.remove());
        };
      })
      .catch(error => console.error('BleManager could not be started.', error));
  }, []);

  const handleAndroidPermissions = () => {
    if (Platform.OS === 'android') {
      const permissions =
        Platform.Version >= 31
          ? [
              PermissionsAndroid.PERMISSIONS.BLUETOOTH_SCAN,
              PermissionsAndroid.PERMISSIONS.BLUETOOTH_CONNECT,
            ]
          : [PermissionsAndroid.PERMISSIONS.ACCESS_FINE_LOCATION];

      PermissionsAndroid.requestMultiple(permissions).then(results => {
        if (
          Object.values(results).every(
            status => status === PermissionsAndroid.RESULTS.GRANTED,
          )
        ) {
          console.debug('[handleAndroidPermissions] Permissions granted');
        } else {
          console.error('[handleAndroidPermissions] Permissions denied');
        }
      });
    }
  };

  const handleDiscoverPeripheral = peripheral => {
    console.debug('[handleDiscoverPeripheral] new BLE peripheral=', peripheral);
    if (!peripheral.name) {
      peripheral.name = 'NO NAME';
    }
    if (
      peripheral.advertising?.serviceUUIDs?.some(
        uuid => uuid.toLowerCase() === serviceUUID.toLowerCase(),
      )
    ) {
      console.debug(
        '[handleDiscoverPeripheral] Audio service found in peripheral:',
        peripheral.id,
      );
      BleManager.stopScan()
        .then(() => {
          console.debug(
            '[handleDiscoverPeripheral] Scanning stopped after finding target UUID.',
          );
          setIsScanning(false);
        })
        .catch(err => {
          console.error('[handleDiscoverPeripheral] Error stopping scan:', err);
        });
    }
    setPeripherals(prev => new Map(prev.set(peripheral.id, peripheral)));
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

  const handleConnectPeripheral = event => {
    console.log(`[handleConnectPeripheral][${event.peripheral}] connected.`);
  };

  const handleDisconnectedPeripheral = event => {
    console.debug(
      `[handleDisconnectedPeripheral][${event.peripheral}] disconnected.`,
    );
    setPeripherals(prev => {
      const p = prev.get(event.peripheral);
      if (p) {
        p.connected = false;
        return new Map(prev.set(event.peripheral, p));
      }
      return prev;
    });
  };

  return (
    <BluetoothContext.Provider
      value={{
        isScanning,
        peripherals,
        startScan,
        bleManagerEmitter,
        togglePeripheralConnection,
      }}>
      {children}
    </BluetoothContext.Provider>
  );
};
