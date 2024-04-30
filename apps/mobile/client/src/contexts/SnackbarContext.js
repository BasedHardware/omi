import { useState, createContext } from 'react';

export const SnackbarContext = createContext();

export const SnackbarProvider = ({ children }) => {
    // Snackbar state
    const [snackbarInfo, setSnackbarInfo] = useState({
        open: false,
        message: '',
        severity: 'info',
    });

    // Function to show snackbar
    const showSnackbar = (message, severity) => {
        setSnackbarInfo({ open: true, message, severity });
    };

    // Function to hide snackbar
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
