import {createBottomTabNavigator} from '@react-navigation/bottom-tabs';
import MomentsStackNavigator from '../navigators/MomentsStackNavigator';
import SettingsStackNavigator from '../navigators/SettingsStackNavigator';
import ChatStackNavigator from '../navigators/ChatStackNavigator';
import {FontAwesomeIcon} from '@fortawesome/react-native-fontawesome';
import {
  faComment,
  faCameraRetro,
  faCog,
} from '@fortawesome/free-solid-svg-icons';

const Tab = createBottomTabNavigator();

const MainScreen = () => {
  return (
    <Tab.Navigator
      screenOptions={{
        tabBarStyle: {
          backgroundColor: '#000',
          borderTopWidth: 0,
          padding: 50,
          height: 120,
          marginBottom: 0
        },
        headerShown: false,
        tabBarLabel: () => null,
      }}>
      <Tab.Screen
        name="Chat"
        component={ChatStackNavigator}
        options={{
          tabBarIcon: ({color}) => (
            <FontAwesomeIcon icon={faComment} size={24} color={color} />
          ),
        }}
      />
      <Tab.Screen
        name="Moments"
        component={MomentsStackNavigator}
        options={{
          tabBarIcon: ({color}) => {
            return (
              <FontAwesomeIcon icon={faCameraRetro} size={24} color={color} />
            );
          },
        }}
      />
      <Tab.Screen
        name="Settings"
        component={SettingsStackNavigator}
        options={{
          tabBarIcon: ({color}) => {
            return <FontAwesomeIcon icon={faCog} size={24} color={color} />;
          },
        }}
      />
    </Tab.Navigator>
  );
};

export default MainScreen;
