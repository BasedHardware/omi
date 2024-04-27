import React from 'react';
import {createNativeStackNavigator} from '@react-navigation/native-stack';
import SettingsTab from '../screens/SettingsTab';

const Stack = createNativeStackNavigator();

const SettingsStackNavigator = () => {
  return (
    <Stack.Navigator initialRouteName="Settings">
      <Stack.Screen name="Settings" component={SettingsTab} />
    </Stack.Navigator>
  );
};

export default SettingsStackNavigator;
