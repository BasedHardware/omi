import {useContext} from 'react';
import {View, Image, Text, StyleSheet} from 'react-native';
import {FontAwesomeIcon} from '@fortawesome/react-native-fontawesome';
import {faUser} from '@fortawesome/free-solid-svg-icons';

const UserMessage = ({message}) => {
  return (
    <View
      style={[
        styles.messageContainer,
        {
          backgroundColor: 'lightgray',
        },
      ]}>
      <FontAwesomeIcon
        icon={faUser}
        size={14}
        color="#666" // Adjust color based on your theme
        style={styles.icon}
      />
      <View style={styles.messageContent}>
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
