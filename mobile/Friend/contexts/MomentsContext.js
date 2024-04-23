import {createContext, useState, useEffect} from 'react';
import EncryptedStorage from 'react-native-encrypted-storage';
import axios from 'axios';
import {BACKEND_URL} from '@env';

export const MomentsContext = createContext();

export const MomentsProvider = ({children}) => {
  const [moments, setMoments] = useState([]);
  const [isLoading, setIsLoading] = useState(false);

  const fetchMoments = async () => {
    setIsLoading(true);
    let momentsData = [];

    // Try fetching moments from local storage
    try {
      const momentsJson = await EncryptedStorage.getItem('moments');
      if (momentsJson) {
        try {
          momentsData = JSON.parse(momentsJson);
        } catch (parseError) {
          console.error('Error parsing moments JSON:', parseError);
        }
      } else {
        console.log('No moments stored locally');
      }
    } catch (storageError) {
      console.error(
        'Failed to retrieve moments from local storage:',
        storageError,
      );
    }

    // Fetch moments from server if local fetch is unsuccessful or empty
    if (momentsData.length === 0) {
      try {
        const response = await axios.get(`${BACKEND_URL}:30000/moments`);
        if (response.status === 200 && response.data) {
          momentsData = response.data.moments;
          setMoments(momentsData);

          try {
            await EncryptedStorage.setItem(
              'moments',
              JSON.stringify(momentsData),
            );
          } catch (storageError) {
            console.error('Failed to update local storage:', storageError);
          }
        } else {
          console.log(
            'Request succeeded but with a non-200 status code:',
            response.status,
          );
        }
      } catch (networkError) {
        console.error('Request failed:', networkError);
      }
    } else {
      // If data is successfully fetched from local storage
      setMoments(momentsData);
    }

    setIsLoading(false);
  };

  const addMoment = async moment => {
    try {
      // Retrieve and parse stored moments
      const momentsJson = await EncryptedStorage.getItem('moments');
      let moments = [];

      if (momentsJson) {
        try {
          moments = JSON.parse(momentsJson);
        } catch (parseError) {
          console.error('Error parsing moments JSON:', parseError);
          // Optionally, handle corrupted data, for example by initializing an empty array.
          moments = [];
        }
      }

      // Add new moment and update storage
      moments.push(moment);
      try {
        await EncryptedStorage.setItem('moments', JSON.stringify(moments));
      } catch (storageError) {
        console.error('Failed to save moments:', storageError);
        throw new Error('Error saving data');
      }

      // Update local state
      setMoments(moments);
    } catch (error) {
      console.error('Error managing local storage for moments:', error);
    }

    // Post new moment to the server
    try {
      const response = await axios.post(`${BACKEND_URL}:30000/moments`, {
        newMoment: moment,
      });
      console.log('Response:', response);
      if (response.status === 200 && response.data) {
        console.log('Success:', response.data);
      } else {
        console.log(
          'Request succeeded but with a non-200 status code:',
          response.status,
        );
      }
    } catch (networkError) {
      console.error('Request failed:', networkError);
    }
  };

  useEffect(() => {
    fetchMoments();
  }, []);

  return (
    <MomentsContext.Provider
      value={{
        moments,
        setMoments,
        isLoading,
        fetchMoments,
        addMoment,
      }}>
      {children}
    </MomentsContext.Provider>
  );
};
