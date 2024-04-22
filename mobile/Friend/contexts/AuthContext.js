import { createContext, useState, useEffect } from 'react';
import EncryptedStorage from 'react-native-encrypted-storage';
import { v4 as uuidv4 } from 'uuid';

export const AuthContext = createContext();

export const AuthProvider = ({ children }) => {
    const [isAuthorized, setIsAuthorized] = useState(false);
    const [isLoading, setIsLoading] = useState(false);
    const [loggedIn, setLoggedIn] = useState(false);

    const fetchUserData = async () => {
        const usersJson = await EncryptedStorage.getItem('users');
        const usersData = JSON.parse(usersJson);
        const firstUserId = Object.keys(usersData)[0];
        const firstUser = usersData[firstUserId];
        return firstUser;
    };

    const registerUser = async (userInfo) => {
        const userId = uuidv4();
        userInfo['userId'] = userId;
        console.log('Registering user:', userInfo);
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
        } catch (error) {
            console.error('Error storing the user info', error);
        }
    };

    useEffect(() => {
        fetchUserData().then((user) => {
            if (user) {
                console.log('User is logged in');
                setIsAuthorized(user.loggedIn);
            }
        });
    }, []);

    const signOut = async () => {
        setIsAuthorized(false);
    };

    /* eslint-disable react/jsx-filename-extension */
    return (
        <AuthContext.Provider
            value={{
                isAuthorized,
                signOut,
                setIsLoading,
                isLoading,
                loggedIn,
                registerUser,
            }}
        >
            {children}
        </AuthContext.Provider>
    );
};
