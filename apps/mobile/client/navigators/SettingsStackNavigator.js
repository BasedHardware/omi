import React from 'react';
import {createNativeStackNavigator} from '@react-navigation/native-stack';
import SettingsTab from '../screens/SettingsTab';
import PeripheralDetailsScreen from '../screens/PeripheralDetailsScreen';

const Stack = createNativeStackNavigator();

const SettingsStackNavigator = () => {
  return (
    <Stack.Navigator initialRouteName="Settings">
      <Stack.Screen name="Settings" component={SettingsTab} />
      <Stack.Screen
        name="Peripheral Details"
        component={PeripheralDetailsScreen}
      />
    </Stack.Navigator>
  );
};

export default SettingsStackNavigator;
