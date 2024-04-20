import { createContext, useState, useEffect } from 'react';
import { auth } from '../firebase_config/firebaseConfig';

export const AuthContext = createContext();

export const AuthProvider = ({ children }) => {
    const [idToken, setIdToken] = useState(null);
    const [uid, setUid] = useState(null);
    const [user, setUser] = useState(null);
    const [isAuthorized, setIsAuthorized] = useState(false);

    useEffect(() => {
        const unsubscribe = auth.onIdTokenChanged(async function (user) {
            if (user) {
                // User is signed in or their token has been refreshed.
                const token = await user.getIdToken();
                setIdToken(token);
                setUid(user.uid);
                setUser(user);
            } else {
                // User is signed out.
                console.log('No user is signed in.');
            }
        });
        return () => unsubscribe();
    }, []);
    return (
        <AuthContext.Provider
            value={{
                idToken,
                setIdToken,
                uid,
                setUid,
                setUser,
                user,
                isAuthorized,
                setIsAuthorized,
            }}
        >
            {children}
        </AuthContext.Provider>
    );
};
