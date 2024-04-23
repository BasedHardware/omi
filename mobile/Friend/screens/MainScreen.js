import {useEffect, useState, useContext} from 'react';
import {Text} from 'react-native';
import {View, StyleSheet} from 'react-native';
import {createBottomTabNavigator} from '@react-navigation/bottom-tabs';
import {Icon} from 'react-native-elements';
import MomentsStackNavigator from '../navigators/MomentsStackNavigator';
import MomentsTab from './MomentsScreen';
const Tab = createBottomTabNavigator();

const ChatTab = () => {
  return (
    <View style={styles.container}>
      <Text>Chat Tab</Text>
    </View>
  );
};

const SettingsTab = () => {
  return (
    <View style={styles.container}>
      <Text>Settings Tab</Text>
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
        name="Settings"
        component={SettingsTab}
        options={{
          tabBarIcon: props => {
            return (
              <Icon name="user-plus" type="font-awesome" color={props.color} />
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
    alignItems: 'center',
    justifyContent: 'center',
  },
});

export default MainScreen;
