import {createNativeStackNavigator} from '@react-navigation/native-stack';
import Chat from '../components/chat/Chat';
import ChatTab from '../screens/ChatTab';

const Stack = createNativeStackNavigator();

const ChatStackNavigator = () => {
  return (
    <Stack.Navigator initialRouteName="ChatMain" screenOptions={{headerStyle: {backgroundColor: '#000'}}}>
      <Stack.Screen
        name="ChatMain"
        component={ChatTab}
        options={{title: 'Chat', headerShown: false}}
      />
      <Stack.Screen name="Chat Room" component={Chat} options={{title: ''}} />
    </Stack.Navigator>
  );
};

export default ChatStackNavigator;
