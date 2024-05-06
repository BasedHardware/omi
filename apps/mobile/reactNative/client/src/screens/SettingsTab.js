import React, {useContext, useState, useEffect} from 'react';
import {
  SafeAreaView,
  StyleSheet,
  View,
  Text,
  FlatList,
  TouchableHighlight,
  Pressable,
} from 'react-native';
import {BluetoothContext} from '../contexts/BluetoothContext';
import {Colors} from 'react-native/Libraries/NewAppScreen';

const SettingsTab = () => {
  const {isScanning, peripherals, startScan, togglePeripheralConnection} =
    useContext(BluetoothContext);

  const renderItem = ({item}) => {
    const backgroundColor = item.connected ? '#069400' : Colors.white;
    return (
      <TouchableHighlight
        underlayColor="transparent"
        onPress={() => togglePeripheralConnection(item)}>
        <View style={[styles.row, {backgroundColor}]}>
          <Text style={styles.peripheralName}>
            {item?.advertising?.localName}
            {item.connecting && ' - Connecting...'}
          </Text>
        </View>
      </TouchableHighlight>
    );
  };

  // Determine initial visibility of the scan button based on peripherals list
  const [showScanButton, setShowScanButton] = useState(peripherals.size === 0);

  // Update button visibility when peripherals list changes
  useEffect(() => {
    setShowScanButton(peripherals.size === 0);
  }, [peripherals.size]);

  return (
    <>
      <SafeAreaView style={styles.container}>
        <View style={styles.buttonGroup}>
          {showScanButton && (
            <Pressable style={styles.scanButton} onPress={startScan}>
              <Text style={styles.scanButtonText}>
                {isScanning ? 'Scanning...' : 'Scan Bluetooth'}
              </Text>
            </Pressable>
          )}
        </View>

        {Array.from(peripherals.values()).length === 0 && (
          <View style={styles.row}>
            <Text style={styles.noPeripherals}>Is your Friend turned On?</Text>
          </View>
        )}

        <FlatList
          data={Array.from(peripherals.values())}
          contentContainerStyle={{rowGap: 12}}
          renderItem={renderItem}
          keyExtractor={item => item.id}
        />
      </SafeAreaView>
    </>
  );
};

const boxShadow = {
  shadowColor: '#000',
  shadowOffset: {
    width: 0,
    height: 2,
  },
  shadowOpacity: 0.25,
  shadowRadius: 3.84,
  elevation: 5,
};

const styles = StyleSheet.create({
  buttonGroup: {
    flexDirection: 'row',
    width: '100%',
  },
  scanButton: {
    alignItems: 'center',
    justifyContent: 'center',
    paddingVertical: 16,
    paddingHorizontal: 16,
    backgroundColor: '#0a398a',
    margin: 10,
    borderRadius: 12,
    flex: 1,
    ...boxShadow,
  },
  scanButtonText: {
    fontSize: 16,
    letterSpacing: 0.25,
    color: Colors.white,
  },
  container: {
    backgroundColor: '#000',
    flex: 1,
  },
  peripheralName: {
    fontSize: 16,
    textAlign: 'center',
    padding: 10,
  },
  row: {
    marginLeft: 10,
    marginRight: 10,
    borderRadius: 20,
    ...boxShadow,
  },
  noPeripherals: {
    margin: 10,
    textAlign: 'center',
    color: Colors.black,
  },
});

export default SettingsTab;
