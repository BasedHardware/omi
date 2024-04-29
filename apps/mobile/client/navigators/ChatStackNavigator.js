import React, {useLayoutEffect} from 'react';
import {createNativeStackNavigator} from '@react-navigation/native-stack';
import Chat from '../components/chat/Chat';
import ChatTab from '../screens/ChatTab';
import {getFocusedRouteNameFromRoute} from '@react-navigation/native';

const Stack = createNativeStackNavigator();

const logoutButton = () => (
  <Button onPress={() => signOut()} title="">
    <FontAwesomeIcon icon={faSignOutAlt} size={24} color="#000" />
  </Button>
);


const ChatStackNavigator = ({navigation, route}) => {
  useLayoutEffect(() => {
    const routeName = getFocusedRouteNameFromRoute(route) ?? 'Chat';
    const showTabBar = routeName === 'Chat';
    navigation.setOptions({
      tabBarStyle: {display: showTabBar ? 'flex' : 'none'},
    });
  }, [navigation, route]);

  return (
    <Stack.Navigator initialRouteName="Chat">
      <Stack.Screen name="Chat" component={ChatTab} />
      <Stack.Screen
        name="Chat Room"
        component={Chat}
        options={{title: ''}}
        headerRight={logoutButton}
      />
    </Stack.Navigator>
  );
};

export default ChatStackNavigator;
