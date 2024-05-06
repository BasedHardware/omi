import React from 'react';
import {createNativeStackNavigator} from '@react-navigation/native-stack';
import MomentsTab from '../screens/MomentsTab';
import MomentDetailScreen from '../screens/MomentDetailScreen';

const Stack = createNativeStackNavigator();

const MomentsStackNavigator = () => {
  return (
    <Stack.Navigator
      initialRouteName="MomentsMain"
      screenOptions={{headerStyle: {backgroundColor: '#000'}}}>
      <Stack.Screen
        name="MomentsMain"
        component={MomentsTab}
        options={{title: 'Moments', headerShown: false}}
      />
      <Stack.Screen
        name="Moment Details"
        component={MomentDetailScreen}
        options={{title: ''}}
      />
    </Stack.Navigator>
  );
};

export default MomentsStackNavigator;
