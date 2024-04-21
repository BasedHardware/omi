import { createContext, useState, useEffect } from 'react';
import * as SecureStore from 'expo-secure-store';
import { v4 as uuidv4 } from 'uuid';

export const AuthContext = createContext();

export const AuthProvider = ({ children }) => {
    const [isAuthorized, setIsAuthorized] = useState(false);
    const [isLoading, setIsLoading] = useState(false);
    const [loggedIn, setLoggedIn] = useState(false);

    const fetchUserData = async () => {
        const usersJson = await SecureStore.getItemAsync('users');
        const usersData = JSON.parse(usersJson);
        const firstUserId = Object.keys(usersData)[0]; 
        const firstUser = usersData[firstUserId]; 
        return firstUser; 
    };

    const registerUser = async (userInfo) => {
        const userId = uuidv4();
        userInfo['userId'] = userId;
        try {
            const usersJson = await SecureStore.getItemAsync('users');
            let users = [];

            if (usersJson) {
                users = JSON.parse(usersJson);
            }

            // Add the new user to the users object
            users[userId] = userInfo;

            await SecureStore.setItemAsync('users', JSON.stringify(users));
            setIsAuthorized(true);
            setLoggedIn(true);
        } catch (error) {
            console.error('Error storing the user info', error);
        }
    };

    useEffect(() => {
        fetchUserData().then((user) => {
            if (user) {
                setIsAuthorized(user.loggedIn);
            }
        });
    }, []);

    const signOut = async () => {
        await SecureStore.deleteItemAsync('userToken');
        setIsAuthorized(false);
    };

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
