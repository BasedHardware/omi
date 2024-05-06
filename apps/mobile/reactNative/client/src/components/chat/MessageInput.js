import React, {useContext, useState, useEffect} from 'react';
import {
  View,
  TextInput,
  TouchableOpacity,
  Image,
  StyleSheet,
} from 'react-native';
import {FontAwesomeIcon} from '@fortawesome/react-native-fontawesome';
import {faPaperPlane} from '@fortawesome/free-solid-svg-icons';
import {ChatContext} from '../../contexts/ChatContext';

const MessageInput = ({chatId}) => {
  const {sendMessage} = useContext(ChatContext);
  const [input, setInput] = useState('');
  const handleSendMessage = () => {
    if (input.trim()) {
      sendMessage(chatId, input);
      setInput('');
    }
  };

  return (
    <View style={styles.inputArea}>
      <View style={styles.inputContainer}>
        <TextInput
          style={styles.inputField}
          multiline
          value={input}
          onChangeText={setInput}
          placeholder="Type Something"
          onSubmitEditing={handleSendMessage}
        />
        <TouchableOpacity
          onPress={handleSendMessage}
          disabled={!input.trim()}
          style={styles.iconButton}
          accessibilityLabel="Send Message">
          <FontAwesomeIcon icon={faPaperPlane} size={24} />
        </TouchableOpacity>
      </View>
    </View>
  );
};

export default MessageInput;

const styles = StyleSheet.create({
  inputContainer: {
    flexDirection: 'row',
    alignItems: 'center',
    backgroundColor: '#fff',
    borderRadius: 25,
    borderWidth: 1,
    borderColor: '#ccc',
    padding: 10,
  },
  inputField: {
    flex: 1,
    minHeight: 50,
    padding: 10,
    borderRadius: 25,
    borderWidth: 0, // Remove border from input field itself
  },
  iconButton: {
    padding: 10,
    marginRight: 5,
  },
});
