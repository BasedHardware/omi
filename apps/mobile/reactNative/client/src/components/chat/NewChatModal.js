import React, {useState, useContext} from 'react';
import {Modal, View, TextInput, Button, StyleSheet} from 'react-native';
import {Picker} from '@react-native-picker/picker';
import {ChatContext} from '../../contexts/ChatContext';
import {AuthContext} from '../../contexts/AuthContext';

const NewChatModal = ({visible, onClose}) => {
  const [chatName, setChatName] = useState('');
  const [model, setModel] = useState('GPT-3.5');
  const {userId} = useContext(AuthContext);
  const {createChat} = useContext(ChatContext);

  const handleCreate = () => {
    createChat(model, chatName, userId);
    onClose();
  };

  return (
    <Modal
      animationType="slide"
      transparent={true}
      visible={visible}
      onRequestClose={onClose}>
      <View style={styles.main}>
        <View style={styles.modalContent}>
          <TextInput
            placeholder="Chat Name"
            placeholderTextColor="#707070"
            value={chatName}
            onChangeText={setChatName}
            style={styles.textInput}
          />
          <Picker
            selectedValue={model}
            style={styles.pickerStyle}
            onValueChange={(itemValue, itemIndex) => setModel(itemValue)}
            mode="dropdown">
            <Picker.Item label="GPT-3.5" value="GPT-3.5" />
            <Picker.Item label="GPT-4" value="GPT-4" />
          </Picker>
          <View style={styles.buttonContainer}>
            <Button title="Cancel" onPress={onClose} />
            <View style={styles.buttonSpacer} />
            <Button title="Create" onPress={handleCreate} />
          </View>
        </View>
      </View>
    </Modal>
  );
};

const styles = StyleSheet.create({
  main: {
    flex: 1,
    justifyContent: 'center',
    alignItems: 'center',
    backgroundColor: 'rgba(0, 0, 0, 0.5)',
  },
  modalContent: {
    margin: 20,
    backgroundColor: 'white',
    borderRadius: 20,
    padding: 35,
    alignItems: 'center',
    shadowColor: '#000',
    shadowOffset: {
      width: 0,
      height: 2,
    },
    shadowOpacity: 0.25,
    shadowRadius: 3.84,
    elevation: 5,
  },
  textInput: {
    height: 40,
    borderColor: 'gray',
    borderRadius: 5,
    borderWidth: 2,
    width: 200,
    marginBottom: 20,
    textAlign: 'center',
  },
  pickerStyle: {
    display: 'flex',
    width: 200,
    height: 'auto',
  },
  buttonContainer: {
    flexDirection: 'row',
    width: '100%',
  },
  buttonSpacer: {
    width: 20,
  },
});

export default NewChatModal;
