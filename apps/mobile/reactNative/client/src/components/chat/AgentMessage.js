import React from 'react';
import {View, Text, StyleSheet} from 'react-native';
import {FontAwesomeIcon} from '@fortawesome/react-native-fontawesome';
import {faRobot} from '@fortawesome/free-solid-svg-icons';
import SyntaxHighlighter from 'react-native-syntax-highlighter';

import {prism} from 'react-syntax-highlighter/styles/prism';

const AgentMessage = ({message}) => {

  return (
    <View style={[styles.messageContainer, {backgroundColor: 'darkgray'}]}>
      <FontAwesomeIcon
        icon={faRobot}
        size={18}
        color="#666" // Adjust color based on your theme
        style={styles.icon}
      />

      <View style={styles.messageContent}>
        {message.map((msg, index) => {
          if (msg.type === 'text') {
            return <Text key={`text${index}`}>{msg.content}</Text>;
          } else if (msg.type === 'code') {
            return (
              <SyntaxHighlighter
                language={msg.language || 'markdown'}
                style={prism}
                highlighter="prism">
                {msg.content}
              </SyntaxHighlighter>
            );
          }
          return null;
        })}
      </View>
    </View>
  );
};

const styles = StyleSheet.create({
  messageContainer: {
    flexDirection: 'row',
    alignItems: 'flex-start',
    padding: 10,
  },
  icon: {
    marginRight: 13,
  },
  messageContent: {
    maxHeight: '100%',
    overflow: 'hidden',
    width: '100%',
    paddingRight: 30,
  },
});

export default AgentMessage;
