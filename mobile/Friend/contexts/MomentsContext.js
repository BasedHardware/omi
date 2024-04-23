import {createContext, useState, useEffect} from 'react';
import EncryptedStorage from 'react-native-encrypted-storage';

export const MomentsContext = createContext();

export const MomentsProvider = ({children}) => {
  const [moments, setMoments] = useState([]);
  const [isLoading, setIsLoading] = useState(false);

  const fetchMoments = async () => {
    setIsLoading(true);
    try {
      const momentsJson = await EncryptedStorage.getItem('moments');
      const momentsData = JSON.parse(momentsJson); // This line can throw if momentsJson is not valid JSON
      setMoments(momentsData);
    } catch (error) {
      console.error('Failed to fetch moments:', error);
      // Handle the error (e.g., set an error state, show a message to the user, etc.)
    } finally {
      setIsLoading(false);
    }
  };

  const addMoment = async moment => {
    const momentsJson = await EncryptedStorage.getItem('moments');
    let moments = [];

    if (momentsJson) {
      moments = JSON.parse(momentsJson);
    }

    moments.push(moment);
    await EncryptedStorage.setItem('moments', JSON.stringify(moments));
    setMoments(moments);
  };

  useEffect(() => {
    // fetchMoments();
  }, []);

  return (
    <MomentsContext.Provider
      value={{
        moments,
        isLoading,
        fetchMoments,
        addMoment,
      }}>
      {children}
    </MomentsContext.Provider>
  );
};
