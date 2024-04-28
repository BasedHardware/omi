import React, {useState, useEffect} from 'react';
import {useNavigation} from '@react-navigation/native';
import {View, FlatList, StyleSheet} from 'react-native';
import { Icon, Text, Button} from 'react-native-elements';
import ChatListItem from '../components/ChatListItem';
import {GestureHandlerRootView} from 'react-native-gesture-handler';
const ChatTab = () => {
  const [chats, setChats] = useState([]);
  const [loading, setLoading] = useState(false);
  const navigation = useNavigation();

  useEffect(() => {
    setLoading(true);
    // Simulate fetching data
    setTimeout(() => {
      setChats([
        {id: '1', title: 'Chat 1', subtitle: 'Last message...'},
        {id: '2', title: 'Chat 2', subtitle: 'Last message...'},
        {id: '3', title: 'Chat 3', subtitle: 'Last message...'},
        // Add more chats as needed
      ]);
      setLoading(false);
    }, 2000);
  }, []);

  // Mock chat data
  const chatData = [
    {
      id: '1',
      title: 'Chat 1',
      summary: 'Last message...',
      text: 'Chat 1',
    },
    {
      id: '2',
      title: 'Chat 2',
      summary: 'Last message...',
      text: 'Chat 2',
    },
    {
      id: '3',
      title: 'Chat 3',
      summary: 'Last message...',
      text: 'Chat 3',
    },
  ];
  const handlePress = item => {
    navigation.navigate('Chat Room', {
      chat_name: item.title,
      summary: item.summary,
      text: item.text,
      chatId: item.id,
    });
  };

  return (
    <GestureHandlerRootView>
      <View style={styles.container}>
        <Button style={styles.button}>
          <Icon name="chat" size={24} color="#fff" />
          <Text style={styles.buttonText}>Create Chat</Text>
        </Button>
        <FlatList
          data={chatData}
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
    backgroundColor: '#007bff',
    padding: 10,
    borderRadius: 5,
    marginHorizontal: 10,
    marginBottom: 20,
  },
  buttonText: {
    color: '#fff',
    marginLeft: 10,
  },
});

export default ChatTab;
