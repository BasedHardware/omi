import React, {useContext} from 'react';
import {View, Image, Text, StyleSheet} from 'react-native';
import {Avatar} from 'react-native-elements';

const UserMessage = ({message}) => {
  return (
    <View
      style={[
        styles.messageContainer,
        {
          backgroundColor: 'blue',
        },
      ]}>
      <Avatar
        rounded
        source={{uri: 'https://example.com/default-avatar.png'}}
        containerStyle={styles.avatar}
      />
      <View style={[styles.messageContent, {alignSelf: 'flex-start'}]}>
        <Text>{message.content}</Text>
      </View>
    </View>
  );
};

export default UserMessage;

const styles = StyleSheet.create({
  messageContainer: {
    flexDirection: 'row',
    alignItems: 'flex-start',
    paddingRight: 50,
    paddingTop: 20,
    paddingBottom: 20,
  },
  avatar: {
    margin: 13,
    width: 33,
    height: 33,
    backgroundColor: 'transparent',
  },
  image: {
    width: 90,
    height: undefined,
    aspectRatio: 1,
  },
  messageContent: {
    maxHeight: '100%',
    overflow: 'hidden',
    width: '100%',
    marginLeft: 10,
  },
});
