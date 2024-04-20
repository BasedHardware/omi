import React, { useContext, useEffect, useState } from 'react';
import { NavigationContainer } from '@react-navigation/native';
import { createNativeStackNavigator } from '@react-navigation/native-stack';
import { AuthContext, AuthProvider } from './contexts/AuthContext';
import AuthStack from './screens/LoginScreen';


const Stack = createNativeStackNavigator();

const AuthenticatedRoutes = () => {
  return (
    <Stack.Navigator>
      {/* Add more authenticated routes here */}
    </Stack.Navigator>
  );
};

const UnauthenticatedRoutes = () => {
  return (
    <Stack.Navigator>
      <Stack.Screen name="Auth" component={AuthStack} options={{ headerShown: false }} />
      {/* Add more unauthenticated routes here */}
    </Stack.Navigator>
  );
};

const App = () => {
  const { isAuthorized } = useContext(AuthContext); // Ensure this context provides isAuthorized or similar flag

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