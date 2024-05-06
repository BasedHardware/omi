import {
  useState,
  createContext,
  useContext,
  useRef,
  useCallback,
  useEffect,
} from 'react';
import axios from 'axios';
import EncryptedStorage from 'react-native-encrypted-storage';
import {processToken} from '../components/chat/utils/processToken';
import {SnackbarContext} from './SnackbarContext';
import {AuthContext} from './AuthContext';

export const ChatContext = createContext();

export const ChatProvider = ({children}) => {
  const {showSnackbar} = useContext(SnackbarContext);
  const {userId} = useContext(AuthContext);
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

  // Add a new user message to the messages state
  const addMessage = async (chatId, newMessage) => {
    setMessages(prevMessageParts => {
      return {
        ...prevMessageParts,
        [chatId]: [...(prevMessageParts[chatId] || []), newMessage],
      };
    });

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

  // Get the messages for a specific chat
  // Sent in as chat history
  const getMessages = chatId => {
    return messages[chatId] || [];
  };

  const getChats = useCallback(async () => {
    if (!userId) {
      return;
    }

    try {
      const cachedChats = await EncryptedStorage.getItem('chatArray');
      if (cachedChats) {
        console.log('Loading chats from cache');
        const parsedChats = JSON.parse(cachedChats);
        setChatArray(parsedChats);

        const cachedMessages = parsedChats.reduce((acc, chat) => {
          if (chat.messages) {
            acc[chat.chatId] = chat.messages;
          }
          return acc;
        }, {});
        setMessages(cachedMessages);

        // Check if the messages object is empty and if so, fetch from the database
        if (Object.values(cachedMessages).length === 0) {
          return fetchChatsFromDB();
        }

        return parsedChats;
      } else {
        // No cached chats, fetch from the database
        return fetchChatsFromDB();
      }
    } catch (error) {
      console.error(error);
      showSnackbar(`Network or fetch error: ${error.message}`, 'error');
    }
  }, [chatUrl, setChatArray, setMessages, showSnackbar, userId]);

  const fetchChatsFromDB = async () => {
    console.log(userId, 'fetching chats');
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

    await EncryptedStorage.setItem('chatArray', JSON.stringify(data));
    return data;
  };

  const sendMessage = async (chatId, input) => {
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
      const response = await sendUserMessage(dataPacket);
      await handleStreamingResponse(response, chatId);
    } catch (error) {
      console.error(error);
      showSnackbar(`Network or fetch error: ${error.message}`, 'error');
    }
  };

  const sendUserMessage = async dataPacket => {
    const response = await fetch(`${chatUrl}/chat/messages`, {
      reactNative: {textStreaming: true},
      method: 'POST',
      headers: {
        'Content-Type': 'application/json',
      },
      body: JSON.stringify(dataPacket),
    });

    if (!response.ok) {
      throw new Error('Failed to send message');
    }
    return response;
  };

  const handleStreamingResponse = async (response, chatId) => {
    const reader = response.body.getReader();
    let completeMessage = '';
    while (true) {
      const {done, value} = await reader.read();
      if (done) {
        break;
      }
      const decodedValue = new TextDecoder('utf-8').decode(value);
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
    await updateMessagesStateAndStorage(chatId, completeMessage);
  };

  const updateMessagesStateAndStorage = async (chatId, completeMessage) => {
    // Update messages state
    setMessages(prevMessages => {
      const updatedMessages = [
        ...(prevMessages[chatId] || []).slice(0, -1),
        {
          content: completeMessage,
          message_from: 'agent',
          type: 'database',
        },
      ];

      const newMessagesState = {
        ...prevMessages,
        [chatId]: updatedMessages,
      };

      // Update chatArray state to reflect the new messages
      setChatArray(prevChatArray => {
        const updatedChatArray = prevChatArray.map(chat => {
          if (chat.chatId === chatId) {
            return {
              ...chat,
              messages: updatedMessages,
            };
          }
          return chat;
        });

        // Save updated chatArray to local storage
        (async () => {
          try {
            await EncryptedStorage.setItem(
              'chatArray',
              JSON.stringify(updatedChatArray),
            );
          } catch (error) {
            console.error('Failed to save chat array:', error);
          }
        })();

        return updatedChatArray;
      });

      return newMessagesState;
    });

    // Save updated messages to local storage
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
  };

  const clearChat = async chatId => {
    try {
      const response = await fetch(`${chatUrl}/chat/messages`, {
        method: 'DELETE',
        headers: {
          'Content-Type': 'application/json',
        },
        body: JSON.stringify({chatId}),
      });

      if (!response.ok) throw new Error('Failed to clear messages');

      // Update the chatArray state
      setChatArray(prevChatArray => {
        const updatedChatArray = prevChatArray.map(chat => {
          if (chat.chatId === chatId) {
            // Clear messages for the matching chat
            return {...chat, messages: []};
          }
          return chat;
        });

        return updatedChatArray;
      });

      // Manage Local Storage
      try {
        const updatedChatArray = chatArray.map(chat => {
          if (chat.chatId === chatId) {
            return {...chat, messages: []};
          }
          return agent;
        });
        await EncryptedStorage.setItem(
          'chatArray',
          JSON.stringify(updatedChatArray),
        );
      } catch (error) {
        console.error('Failed to save agent array:', error);
      }

      // Update the messages state for the UI to reflect the cleared messages
      setMessages(prevMessages => {
        const updatedMessages = {...prevMessages, [chatId]: []};
        // No need to update 'messages' in local storage since it's part of 'chatArray'
        return updatedMessages;
      });
    } catch (error) {
      console.error(error);
      showSnackbar(`Network or fetch error: ${error.message}`, 'error');
    }
  };

  const deleteChat = async chatId => {
    try {
      const response = await axios.delete(`${chatUrl}/chat`, {
        headers: {
          'Content-Type': 'application/json',
        },
        data: {chatId},
      });

      if (response.status !== 200)
        throw new Error('Failed to delete conversation');

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
          'chatArray',
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
      // Update the chatArray directly here
      setChatArray(prevChats => {
        const updatedChatArray = [data, ...prevChats];
        return updatedChatArray;
      });

      try {
        const updatedChatArray = [data, ...chatArray];
        await EncryptedStorage.setItem(
          'chatArray',
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

  useEffect(() => {
    // EncryptedStorage.removeItem('chatArray');
    getChats()
      .then(() => {
        setLoading(false);
      })
      .catch(error => {
        console.error('Error fetching chats:', error);
        setLoading(false);
      });
  }, [userId]);

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
