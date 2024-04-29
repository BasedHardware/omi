import {createContext, useState, useEffect, useContext} from 'react';
import EncryptedStorage from 'react-native-encrypted-storage';
import {v4 as uuidv4} from 'uuid';
import {SnackbarContext} from './SnackbarContext';

export const AuthContext = createContext();

export const AuthProvider = ({children}) => {
  const [isAuthorized, setIsAuthorized] = useState(false);
  const [isLoading, setIsLoading] = useState(false);
  const [loggedIn, setLoggedIn] = useState(false);
  const [userId, setUserId] = useState(null);
  const {showSnackbar} = useContext(SnackbarContext);

  const registerUser = async userInfo => {
    const userId = uuidv4();
    userInfo['userId'] = userId;
    userInfo['isLoggedIn'] = true;
    try {
      const usersJson = await EncryptedStorage.getItem('users');
      let users = {};

      if (usersJson) {
        users = JSON.parse(usersJson);
      }

      users[userId] = userInfo;
      console.log('Users:', users);

      await EncryptedStorage.setItem('users', JSON.stringify(users));
      setIsAuthorized(true);
      setLoggedIn(true);
      setUserId(userId);
    } catch (error) {
      showSnackbar('Error storing the user info', 'error');
      console.error('Error storing the user info', error);
    }
  };

  const signOut = async () => {
    const usersJson = await EncryptedStorage.getItem('users');
    if (usersJson) {
      const users = JSON.parse(usersJson);
      const loggedInUser = Object.values(users).find(user => user.isLoggedIn);
      if (loggedInUser) {
        loggedInUser.isLoggedIn = false;
        await EncryptedStorage.setItem('users', JSON.stringify(users));
      }
    }
    setIsAuthorized(false);
    setLoggedIn(false);
    setUserId(null);
  };

  const signIn = async (email, password) => {
    const usersJson = await EncryptedStorage.getItem('users');
    if (!usersJson) {
      showSnackbar('User not found', 'error');
      return;
    }

    const users = JSON.parse(usersJson);
    console.log('Users:', users);
    const user = Object.values(users).find(user => user.email === email);

    if (!user) {
      console.log('User not found');
      showSnackbar('User not found', 'error');
      return;
    }

    if (user.password === password) {
      user.isLoggedIn = true;
      await EncryptedStorage.setItem('users', JSON.stringify(users));
      setIsAuthorized(true);
      setLoggedIn(true);
      setUserId(user.userId);
      showSnackbar('Login successful', 'success');
      return;
    } else {
      showSnackbar('Invalid password', 'error');
      return;
    }
  };

  useEffect(() => {
    const rehydrateUser = async () => {
      const usersJson = await EncryptedStorage.getItem('users');
      if (usersJson) {
        const users = JSON.parse(usersJson);
        const loggedInUser = Object.values(users).find(user => user.isLoggedIn);
        if (loggedInUser) {
          console.log('User is logged in:', loggedInUser);
          setUserId(loggedInUser.userId);
          setIsAuthorized(true);
          setLoggedIn(true);
        }
      }
    };

    rehydrateUser();
  }, []);

  return (
    <AuthContext.Provider
      value={{
        isAuthorized,
        signIn,
        signOut,
        setIsLoading,
        isLoading,
        loggedIn,
        registerUser,
        userId,
      }}>
      {children}
    </AuthContext.Provider>
  );
};
