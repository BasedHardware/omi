import React, {useContext, useEffect, useRef} from 'react';
import {
  ScrollView,
  StyleSheet,
  SafeAreaView,
  KeyboardAvoidingView,
} from 'react-native';
import {ChatContext} from '../../contexts/ChatContext';
import {formatBlockMessage} from './utils/messageFormatter';
import AgentMessage from './AgentMessage';
import MessageInput from './MessageInput';
import UserMessage from './UserMessage';
import ChatBar from './ChatBar';

const styles = StyleSheet.create({
  container: {
    flex: 1, // This makes the container use all available space
    flexDirection: 'column',
  },
  messagesContainer: {
    flex: 1, // This makes the ScrollView expand to fill the space between ChatBar and MessageInput
  },
});

const Chat = ({route}) => {
  const {chat_name: chatName, chatId} = route.params;
  const nodeRef = useRef(null);
  const {messages} = useContext(ChatContext);
  

  // scrolls chat window to the bottom
  useEffect(() => {
    const node = nodeRef.current;
    if (node) {
      node.scrollToEnd({animated: true});
    }
  }, [messages]);

  return (
    <SafeAreaView style={styles.container}>
      <KeyboardAvoidingView
        style={{flex: 1}}
        behavior={Platform.OS === 'ios' ? 'padding' : 'height'}
        keyboardVerticalOffset={Platform.OS === 'ios' ? 100 : 20}>
        <ChatBar chatName={chatName} chatId={chatId} />
        <ScrollView ref={nodeRef} style={styles.messagesContainer}>
          {messages[chatId]?.map((message, index) => {
            let formattedMessage = message;
            if (message.type === 'database') {
              if (message.message_from === 'agent') {
                formattedMessage = formatBlockMessage(message);
                return (
                  <AgentMessage
                    key={`agent${index}`}
                    message={formattedMessage}
                    id={chatId}
                  />
                );
              } else {
                return <UserMessage key={`user${index}`} message={message} />;
              }
            } else {
              return <AgentMessage key={`stream${index}`} message={message} />;
            }
          })}
        </ScrollView>
        <MessageInput chatId={chatId} />
      </KeyboardAvoidingView>
    </SafeAreaView>
  );
};

export default Chat;
