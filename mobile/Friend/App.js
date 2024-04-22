import 'react-native-get-random-values';
import 'url-polyfill';
import React, {useContext, useEffect, useState} from 'react';
import {NavigationContainer} from '@react-navigation/native';
import {createNativeStackNavigator} from '@react-navigation/native-stack';
import {AuthContext, AuthProvider} from './contexts/AuthContext';
import AuthScreen from './screens/AuthScreen';
import MainScreen from './screens/MainScreen';

const Stack = createNativeStackNavigator();

const AuthenticatedRoutes = () => {
  return (
    <Stack.Navigator>
      <Stack.Screen
        name="Main"
        component={MainScreen}
        options={{headerShown: false}}
      />
    </Stack.Navigator>
  );
};

const UnauthenticatedRoutes = () => {
  return (
    <Stack.Navigator>
      <Stack.Screen
        name="Auth"
        component={AuthScreen}
        options={{headerShown: false}}
      />
    </Stack.Navigator>
  );
};

const App = () => {
  const {isAuthorized} = useContext(AuthContext); // Ensure this context provides isAuthorized or similar flag

  return (
    <NavigationContainer>
      {isAuthorized ? <AuthenticatedRoutes /> : <UnauthenticatedRoutes />}
    </NavigationContainer>
  );
};

export default () => (
  <AuthProvider>
    <App />
  </AuthProvider>
);
