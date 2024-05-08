import React, {createContext} from 'react';
import {useChatManager} from '../hooks/useChatManager';

export const ChatContext = createContext();

export const ChatProvider = ({children}) => {
  const chatManager = useChatManager();

  return (
    <ChatContext.Provider value={chatManager}>{children}</ChatContext.Provider>
  );
};
