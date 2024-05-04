import {useContext} from 'react';
import {Button} from 'react-native-elements';
import {createNativeStackNavigator} from '@react-navigation/native-stack';
import SettingsTab from '../screens/SettingsTab';
import {FontAwesomeIcon} from '@fortawesome/react-native-fontawesome';
import {faSignOutAlt} from '@fortawesome/free-solid-svg-icons';
import {AuthContext} from '../contexts/AuthContext';

const Stack = createNativeStackNavigator();
const logoutButton = signOut => (
  <Button
    buttonStyle={{backgroundColor: 'transparent'}}
    onPress={() => signOut()}
    icon={<FontAwesomeIcon icon={faSignOutAlt} size={24} color="#000" />}
  />
);

const SettingsStackNavigator = () => {
  const {signOut} = useContext(AuthContext);
  return (
    <Stack.Navigator initialRouteName="Settings">
      <Stack.Screen
        name="Settings"
        component={SettingsTab}
        options={{
          headerRight: () => logoutButton(signOut),
        }}
      />
    </Stack.Navigator>
  );
};

export default SettingsStackNavigator;
