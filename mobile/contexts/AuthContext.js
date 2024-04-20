import { createContext, useState, useEffect } from 'react';
import * as SecureStore from 'expo-secure-store';

export const AuthContext = createContext();

export const AuthProvider = ({ children }) => {
    const [isAuthorized, setIsAuthorized] = useState(false);

    useEffect(() => {
        const checkAuth = async () => {
            const token = await SecureStore.getItemAsync('userToken');
            setIsAuthorized(!!token);
        };
        checkAuth();
    }, []);

    const authenticateUser = async () => {
        // This function would be triggered to authenticate the user
        // For example, after a PIN is entered or a setup process is completed
        await SecureStore.setItemAsync('userToken', 'yourTokenValue');
        setIsAuthorized(true);
    };

    const signOut = async () => {
        await SecureStore.deleteItemAsync('userToken');
        setIsAuthorized(false);
    };

    return (
        <AuthContext.Provider
            value={{
                isAuthorized,
                authenticateUser,
                signOut,
            }}
        >
            {children}
        </AuthContext.Provider>
    );
};