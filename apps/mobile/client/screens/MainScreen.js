import {StyleSheet, View, Text} from 'react-native';
import {createBottomTabNavigator} from '@react-navigation/bottom-tabs';
import {Icon} from 'react-native-elements';
import MomentsStackNavigator from '../navigators/MomentsStackNavigator';
import SettingsStackNavigator from '../navigators/SettingsStackNavigator';

const Tab = createBottomTabNavigator();

const ChatTab = () => {
  return (
    <View style={styles.container}>
      <Text>Chat Tab</Text>
    </View>
  );
};

const MainScreen = ({navigation}) => {
  return (
    <Tab.Navigator>
      <Tab.Screen
        name="Chat"
        component={ChatTab}
        options={{
          tabBarIcon: props => {
            return (
              <Icon name="user-plus" type="font-awesome" color={props.color} />
            );
          },
        }}
      />
      <Tab.Screen
        name="Moments Tab"
        component={MomentsStackNavigator}
        options={{
          tabBarIcon: props => {
            return (
              <Icon name="user-plus" type="font-awesome" color={props.color} />
            );
          },
          headerShown: false,
        }}
      />
      <Tab.Screen
        name="Settings Tab"
        component={SettingsStackNavigator}
        options={{
          tabBarIcon: props => {
            return (
              <Icon name="user-plus" type="font-awesome" color={props.color} />
            );
          },
          headerShown: false,
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
