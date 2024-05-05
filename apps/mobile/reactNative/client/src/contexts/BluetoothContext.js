import React, {createContext} from 'react';
import {useBluetoothManager} from '../hooks/useBluetoothManager';

export const BluetoothContext = createContext();

export const BluetoothProvider = ({children}) => {
  const bluetoothManager = useBluetoothManager();

  return (
    <BluetoothContext.Provider value={bluetoothManager}>
      {children}
    </BluetoothContext.Provider>
  );
};
