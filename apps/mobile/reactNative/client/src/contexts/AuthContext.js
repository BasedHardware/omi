import {createContext} from 'react';
import {useAuthentication} from '../hooks/useAuthentication';

export const AuthContext = createContext();

export const AuthProvider = ({children}) => {
  const auth = useAuthentication();

  return <AuthContext.Provider value={auth}>{children}</AuthContext.Provider>;
};
