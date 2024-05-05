import React from 'react';
import {createNativeStackNavigator} from '@react-navigation/native-stack';
import MomentsTab from '../screens/MomentsTab';
import MomentDetailScreen from '../screens/MomentDetailScreen';

const Stack = createNativeStackNavigator();

const MomentsStackNavigator = () => {
  return (
    <Stack.Navigator initialRouteName="Moments">
      <Stack.Screen name="Moments" component={MomentsTab} />
      <Stack.Screen name="Moment Details" component={MomentDetailScreen} />
    </Stack.Navigator>
  );
};

export default MomentsStackNavigator;
