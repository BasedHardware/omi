import { useState, createContext } from 'react';

export const SnackbarContext = createContext();

export const SnackbarProvider = ({ children }) => {
    const [snackbarInfo, setSnackbarInfo] = useState({
        open: false,
        message: '',
        severity: 'info',
    });

    const showSnackbar = (message, severity) => {
        setSnackbarInfo({ open: true, message, severity });
    };

    const hideSnackbar = () => {
        setSnackbarInfo({ ...snackbarInfo, open: false });
    };

    return (
        <SnackbarContext.Provider
            value={{
                showSnackbar,
                hideSnackbar,
                snackbarInfo,
            }}
        >
            {children}
        </SnackbarContext.Provider>
    );
};
