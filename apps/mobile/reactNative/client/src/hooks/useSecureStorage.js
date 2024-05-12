import EncryptedStorage from 'react-native-encrypted-storage';

export const useSecureStorage = () => {
  // use for dev purposes
  const deleteUserData = async () => {
    await EncryptedStorage.removeItem('users');
  };
  const deleteMoments = async () => {
    await EncryptedStorage.removeItem('moments');
  };

  const storeItem = async (item, data) => {
    try {
      await EncryptedStorage.setItem(item, JSON.stringify(data));
    } catch (error) {
      console.error('Failed to save users:', error);
      showSnackbar('Failed to save user data', 'error');
    }
  };

  const retrieveItem = async item => {
    try {
      const jsonItem = await EncryptedStorage.getItem(item);
      return jsonItem ? JSON.parse(jsonItem) : null;
    } catch (error) {
      console.error('Failed to retrieve users:', error);
      showSnackbar('Failed to retrieve user data', 'error');
    }
  };

  const clearLocalChat = async chatId => {
    try {
      const chatArray = await retrieveItem('chatArray');
      const updatedChatArray = chatArray.map(chat => {
        if (chat.chatId === chatId) {
          return {...chat, messages: []};
        }
        return chat;
      });
      await EncryptedStorage.setItem(
        'chatArray',
        JSON.stringify(updatedChatArray),
      );
    } catch (error) {
      console.error('Failed to save agent array:', error);
    }
  };

  const deleteLocalChat = async chatId => {
    try {
      const chatArray = await retrieveItem('chatArray');
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
  };

  return {
    storeItem,
    retrieveItem,
    clearLocalChat,
    deleteLocalChat,
    deleteUserData,
    deleteMoments,
  };
};
