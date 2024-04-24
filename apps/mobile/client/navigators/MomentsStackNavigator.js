import React from 'react';
import {createNativeStackNavigator} from '@react-navigation/native-stack';
import MomentsScreen from '../screens/MomentsScreen';
import MomentDetailScreen from '../screens/MomentDetailScreen';

const Stack = createNativeStackNavigator();

const MomentsStackNavigator = () => {
  return (
    <Stack.Navigator initialRouteName="Moments">
      <Stack.Screen name="Moments" component={MomentsScreen} />
      <Stack.Screen
        name="Moment Details"
        component={MomentDetailScreen}
        // Adjust header options as needed
      />
    </Stack.Navigator>
  );
};

export default MomentsStackNavigator;
