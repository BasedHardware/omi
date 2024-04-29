import {
  useState,
  createContext,
  useContext,
  useRef,
  useCallback,
  useEffect,
} from 'react';
import axios from 'axios';
import {processToken} from '../components/chat/utils/processToken';
import {SnackbarContext} from '../contexts/SnackbarContext';
export const ChatContext = createContext();

import EncryptedStorage from 'react-native-encrypted-storage';

export const ChatProvider = ({children}) => {
  const {showSnackbar} = useContext(SnackbarContext);
  const [chatArray, setChatArray] = useState([]);
  const [messages, setMessages] = useState({});
  const [insideCodeBlock, setInsideCodeBlock] = useState(false);
  const [loading, setLoading] = useState(true);
  const ignoreNextTokenRef = useRef(false);
  const languageRef = useRef(null);
  const chatUrl =
    process.env.NODE_ENV === 'development'
      ? 'http://192.168.86.242:30000'
      : process.env.REACT_APP_BACKEND_URL_PROD;

  // Used to add a new user message to the messages state
  const addMessage = async (chatId, newMessage) => {
    setMessages(prevMessageParts => {
      return {
        ...prevMessageParts,
        [chatId]: [...(prevMessageParts[chatId] || []), newMessage],
      };
    });

    // Perform the asynchronous storage operation after updating the state
    const updatedMessages = {
      ...messages,
      [chatId]: [...(messages[chatId] || []), newMessage],
    };
    try {
      await EncryptedStorage.setItem(
        'messages',
        JSON.stringify(updatedMessages),
      );
    } catch (error) {
      console.error('Failed to save messages:', error);
    }
  };

  // Used to get the messages for a specific chat
  // Sent in as chat history
  const getMessages = chatId => {
    return messages[chatId] || [];
  };

  const getChats = useCallback(async () => {
    try {
      const cachedChats = await EncryptedStorage.getItem('agentArray');
      if (cachedChats) {
        const parsedChats = JSON.parse(cachedChats);
        console.log('parsedChats', parsedChats);
        setChatArray(parsedChats);

        const cachedMessages = parsedChats.reduce((acc, chat) => {
          if (chat.messages) {
            acc[chat.chatId] = chat.messages;
          }
          return acc;
        }, {});
        setMessages(cachedMessages);

        return parsedChats;
      }

      const response = await axios.get(`${chatUrl}/chat`, {
        headers: {
          'Content-Type': 'application/json',
          userId: userId,
        },
      });

      if (response.status !== 200)
        throw new Error('Failed to load user conversations');

      const data = response.data;
      setChatArray(data);

      const messagesFromData = data.reduce((acc, chat) => {
        if (chat.messages) {
          acc[chat.chatId] = chat.messages;
        }
        return acc;
      }, {});
      setMessages(messagesFromData);

      await EncryptedStorage.setItem('agentArray', JSON.stringify(data));
      return data;
    } catch (error) {
      console.error(error);
      showSnackbar(`Network or fetch error: ${error.message}`, 'error');
    }
  }, [chatUrl, setChatArray, setMessages, showSnackbar]);

  const sendMessage = async (chatId, input) => {
    // Optimistic update
    const userMessage = {
      content: input,
      message_from: 'user',
      time_stamp: new Date().toISOString(),
      type: 'database',
    };
    addMessage(chatId, userMessage);

    const chatHistory = await getMessages(chatId);

    const dataPacket = {
      chatId,
      userMessage,
      chatHistory,
    };

    try {
      const response = await fetch(`${chatUrl}/chat/messages`, {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
        },
        body: JSON.stringify(dataPacket),
      });

      if (!response.ok) {
        throw new Error('Failed to send message');
      }

      const reader = response.body.getReader();
      let completeMessage = '';
      while (true) {
        const {done, value} = await reader.read();
        if (done) {
          break;
        }
        const decodedValue = new TextDecoder('utf-8').decode(value);
        
        // Split the decoded value by newline and filter out any empty lines
        const jsonChunks = decodedValue
          .split('\n')
          .filter(line => line.trim() !== '');

        const messages = jsonChunks.map(chunk => {
          const messageObj = JSON.parse(chunk);
          processToken(
            messageObj,
            setInsideCodeBlock,
            insideCodeBlock,
            setMessages,
            chatId,
            ignoreNextTokenRef,
            languageRef,
          );
          return messageObj.content;
        });
        completeMessage += messages.join('');
      }
      // While streaming an array of objects is being built for the stream.
      // This sets that array to a message object in the state
      setMessages(prevMessages => {
        const updatedMessages = prevMessages[chatId].slice(0, -1);
        updatedMessages.push({
          content: completeMessage,
          message_from: 'agent',
          type: 'database',
        });

        const newMessagesState = {
          ...prevMessages,
          [chatId]: updatedMessages,
        };

        return newMessagesState;
      });

      // Perform the asynchronous storage operation after updating the state
      try {
        const updatedMessages = {
          ...messages,
          [chatId]: [
            ...(messages[chatId] || []).slice(0, -1),
            {
              content: completeMessage,
              message_from: 'agent',
              type: 'database',
            },
          ],
        };
        await EncryptedStorage.setItem(
          'messages',
          JSON.stringify(updatedMessages),
        );
      } catch (error) {
        console.error('Failed to save messages:', error);
      }
    } catch (error) {
      console.error(error);
      showSnackbar(`Network or fetch error: ${error.message}`, 'error');
    }
  };

  const clearChat = async chatId => {
    try {
      const response = await fetch(`${messagesUrl}/messages/clear`, {
        method: 'DELETE',
        headers: {
          Authorization: idToken,
          'Content-Type': 'application/json',
        },
        body: JSON.stringify({chatId}),
      });

      if (!response.ok) throw new Error('Failed to clear messages');

      // Update the agentArray state
      setChatArray(prevAgentArray => {
        const updatedAgentArray = prevAgentArray.map(agent => {
          if (agent.chatId === chatId) {
            // Clear messages for the matching chat
            return {...agent, messages: []};
          }
          return agent;
        });

        return updatedAgentArray;
      });

      // Perform the asynchronous storage operation after updating the state
      try {
        const updatedAgentArray = chatArray.map(agent => {
          if (agent.chatId === chatId) {
            return {...agent, messages: []};
          }
          return agent;
        });
        await EncryptedStorage.setItem(
          'agentArray',
          JSON.stringify(updatedAgentArray),
        );
      } catch (error) {
        console.error('Failed to save agent array:', error);
      }

      // Update the messages state for the UI to reflect the cleared messages
      setMessages(prevMessages => {
        const updatedMessages = {...prevMessages, [chatId]: []};
        // No need to update 'messages' in local storage since it's part of 'agentArray'
        return updatedMessages;
      });
    } catch (error) {
      console.error(error);
      showSnackbar(`Network or fetch error: ${error.message}`, 'error');
    }
  };

  const deleteChat = async chatId => {
    try {
      const response = await fetch(`${chatUrl}/chat/delete`, {
        method: 'DELETE',
        headers: {
          'Content-Type': 'application/json',
          Authorization: idToken,
        },
        body: JSON.stringify({chatId}),
      });

      if (!response.ok) throw new Error('Failed to delete conversation');

      setChatArray(prevChatArray => {
        const updatedChatArray = prevChatArray.filter(
          chatObj => chatObj.chatId !== chatId,
        );

        return updatedChatArray;
      });

      // Perform the asynchronous storage operation after updating the state
      try {
        const updatedChatArray = chatArray.filter(
          chatObj => chatObj.chatId !== chatId,
        );
        await EncryptedStorage.setItem(
          'agentArray',
          JSON.stringify(updatedChatArray),
        );
      } catch (error) {
        console.error('Failed to save agent array:', error);
      }
    } catch (error) {
      console.error(error);
      showSnackbar(`Network or fetch error: ${error.message}`, 'error');
    }
  };

  const createChat = async (model, chatName, userId) => {
    console.log('createChat', model, chatName, userId);
    try {
      const response = await axios.post(
        `${chatUrl}/chat`,
        {
          model,
          chatName,
          userId,
        },
        {
          headers: {
            'Content-Type': 'application/json',
          },
        },
      );

      if (response.status !== 200) throw new Error('Failed to create chat');

      const data = await response.data;
      // Update the agentArray directly here
      setChatArray(prevAgents => {
        const updatedAgentArray = [data, ...prevAgents];
        return updatedAgentArray;
      });

      try {
        const updatedAgentArray = [data, ...chatArray];
        await EncryptedStorage.setItem(
          'agentArray',
          JSON.stringify(updatedAgentArray),
        );
      } catch (error) {
        console.error('Failed to save agent array:', error);
      }
    } catch (error) {
      console.error(error);
      showSnackbar(`Network or fetch error: ${error.message}`, 'error');
    }
  };

  useEffect(() => {
    getChats().then(() => {
      setLoading(false);
    });
  }, []);

  return (
    <ChatContext.Provider
      value={{
        chatArray,
        setChatArray,
        messages,
        sendMessage,
        clearChat,
        deleteChat,
        createChat,
        getChats,
      }}>
      {children}
    </ChatContext.Provider>
  );
};
