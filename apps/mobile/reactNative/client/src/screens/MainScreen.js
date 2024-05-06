import {StyleSheet} from 'react-native';
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
        tabBarStyle: {backgroundColor: '#000'},
        headerShown: false,
      }}>
      <Tab.Screen
        name="Chat Tab"
        component={ChatStackNavigator}
        options={{
          tabBarIcon: ({color}) => (
            <FontAwesomeIcon icon={faComment} size={24} color={color} />
          ),
        }}
      />
      <Tab.Screen
        name="Moments Tab"
        component={MomentsStackNavigator}
        options={{
          tabBarIcon: props => {
            return (
              <FontAwesomeIcon
                icon={faCameraRetro}
                size={24}
                color={props.color}
              />
            );
          },
        }}
      />
      <Tab.Screen
        name="Settings Tab"
        component={SettingsStackNavigator}
        options={{
          tabBarIcon: props => {
            return (
              <FontAwesomeIcon icon={faCog} size={24} color={props.color} />
            );
          },
        }}
      />
    </Tab.Navigator>
  );
};

const styles = StyleSheet.create({
  container: {
    flex: 1,
    justifyContent: 'center',
    alignItems: 'center',
    margin: 10,
  },
});

export default MainScreen;
