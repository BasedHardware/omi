import React, {useContext, useState} from 'react';
import {View, Text, TouchableOpacity, StyleSheet} from 'react-native';
import {FontAwesomeIcon} from '@fortawesome/react-native-fontawesome';
import {faCommentSlash} from '@fortawesome/free-solid-svg-icons';

import {ChatContext} from '../../contexts/ChatContext';

const ChatBar = ({chatId}) => {
  const {clearChat} = useContext(ChatContext);

  return (
    <View style={styles.iconGroup}>
      <TouchableOpacity
        onPress={() => clearChat(chatId)}
        style={styles.iconButton}>
        <FontAwesomeIcon icon={faCommentSlash} size={20} />
      </TouchableOpacity>
    </View>
  );
};

export default ChatBar;

const styles = StyleSheet.create({
  iconGroup: {
    display: 'flex',
    flexDirection: 'row',
    justifyContent: 'flex-end',
    width: '100%',
  },
  iconButton: {
    padding: 10,
  },
});
