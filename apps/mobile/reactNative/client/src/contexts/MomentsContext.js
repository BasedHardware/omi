import {createContext} from 'react';
import {useMomentsManager} from '../hooks/useMomentsManager';
export const MomentsContext = createContext();

export const MomentsProvider = ({children}) => {
  const momentsManager = useMomentsManager();

  return (
    <MomentsContext.Provider value={momentsManager}>
      {children}
    </MomentsContext.Provider>
  );
};
