import React, {useState, useEffect, useContext} from 'react';
import {useNavigation} from '@react-navigation/native';
import {View, FlatList, StyleSheet} from 'react-native';
import {Button} from 'react-native-elements';
import ChatListItem from '../components/chat/ChatListItem';
import {GestureHandlerRootView} from 'react-native-gesture-handler';
import {FontAwesomeIcon} from '@fortawesome/react-native-fontawesome';
import {faPlus} from '@fortawesome/free-solid-svg-icons';
import {ChatContext} from '../contexts/ChatContext';

import NewChatModal from '../components/chat/NewChatModal';

const ChatTab = () => {
  const {chatArray} = useContext(ChatContext);
  const [modalVisible, setModalVisible] = useState(false);
  const navigation = useNavigation();

  const handlePress = item => {
    navigation.navigate('Chat Room', {
      chat_name: item.chat_name,
      chatId: item.chatId,
      messages: item.messages,
    });
  };

  return (
    <GestureHandlerRootView>
      <View style={styles.container}>
        <Button
          icon={<FontAwesomeIcon icon={faPlus} size={24} color="#000" />}
          title="Create Chat"
          buttonStyle={styles.button}
          titleStyle={styles.buttonText}
          onPress={() => setModalVisible(true)}
        />
        <NewChatModal
          visible={modalVisible}
          onClose={() => setModalVisible(false)}
        />
        <FlatList
          data={chatArray}
          keyExtractor={(item, index) => index.toString()}
          renderItem={({item}) => (
            <ChatListItem item={item} onItemPress={handlePress} />
          )}
          style={{flex: 1}}
        />
      </View>
    </GestureHandlerRootView>
  );
};

const styles = StyleSheet.create({
  container: {
    flex: 1,
    marginTop: 20,
  },
  button: {
    flexDirection: 'row',
    alignItems: 'center',
    backgroundColor: 'transparent',
    borderColor: '#000',
    borderWidth: 2,
    padding: 10,
    borderRadius: 5,
    marginHorizontal: 10,
    marginBottom: 20,
    width: '50%',
    alignSelf: 'center',
  },
  buttonText: {
    color: '#000',
    marginLeft: 10,
  },
});

export default ChatTab;
