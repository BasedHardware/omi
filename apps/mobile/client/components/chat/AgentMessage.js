import React from 'react';
import {View, Text, StyleSheet} from 'react-native';
import {FontAwesomeIcon} from '@fortawesome/react-native-fontawesome';
import {faRobot} from '@fortawesome/free-solid-svg-icons';

const AgentMessage = ({message}) => {
  return (
    <View
      style={[
        styles.messageContainer,
        {
          backgroundColor: 'red',
        },
      ]}>
      <FontAwesomeIcon
        icon={faRobot}
        size={36}
        color="#666" // Adjust color based on your theme
        style={styles.icon}
      />

      <View style={styles.messageContent}>
        {message.map((msg, index) => {
          if (msg.type === 'text') {
            return <Text key={`text${index}`}>{msg.content}</Text>;
          } else if (msg.type === 'code') {
            // For code, you might want to use a custom component or library that supports syntax highlighting
            return <Text key={`code${index}`}>{msg.content}</Text>;
          }
          return null;
        })}
      </View>
    </View>
  );
};

export default AgentMessage;

const styles = StyleSheet.create({
  messageContainer: {
    flexDirection: 'row',
    alignItems: 'flex-start',
    paddingRight: 50,
    paddingTop: 20,
    paddingBottom: 20,
  },
  icon: {
    marginRight: 13,
  },
  messageContent: {
    maxHeight: '100%',
    overflow: 'hidden',
    width: '100%',
  },
});
