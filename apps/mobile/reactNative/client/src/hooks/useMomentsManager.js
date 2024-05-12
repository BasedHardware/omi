import {useState, useContext, useEffect} from 'react';
import axios from 'axios';
import {BACKEND_URL} from '@env';
import {SnackbarContext} from '../contexts/SnackbarContext';
import {useSecureStorage} from './useSecureStorage';

export const useMomentsManager = () => {
  const [moments, setMoments] = useState([]);
  const [isLoading, setIsLoading] = useState(false);
  const {storeItem, retrieveItem, deleteMoments} = useSecureStorage();
  const {showSnackbar} = useContext(SnackbarContext);

  useEffect(() => {
    // deleteMoments();
    fetchMoments();
  }, []);

  const fetchMoments = async () => {
    setIsLoading(true);
    let momentsData = await retrieveItem('moments');

    if (!momentsData || momentsData.length === 0) {
      try {
        const response = await axios.get(`${BACKEND_URL}:30001/moments`);
        if (response.status === 200 && response.data) {
          momentsData = response.data.moments;
          await storeItem('moments', momentsData);
        }
      } catch (error) {
        console.error('Error fetching moments:', error);
        showSnackbar('Error fetching moments', 'error');
      }
    }

    setMoments(momentsData);
    setIsLoading(false);
  };

  const addMoment = async moment => {
    try {
      const response = await axios.post(`${BACKEND_URL}:30001/moments`, {
        newMoment: moment,
      });
      if (response.status === 200 && response.data) {
        const updatedMoments = (await retrieveItem('moments')) || [];
        updatedMoments.push(response.data.moment);
        await storeItem('moments', updatedMoments);
        setMoments(updatedMoments);
        return response.data.moment.momentId;
      }
    } catch (error) {
      console.error('Error adding moment:', error);
      showSnackbar('Error adding moment', 'error');
    }
  };

  const updateMoment = async moment => {
    try {
      const response = await axios.put(`${BACKEND_URL}:30001/moments`, {
        moment,
      });
      if (response.status === 200 && response.data) {
        const updatedMoments = (await retrieveItem('moments')) || [];
        const index = updatedMoments.findIndex(
          item => item.momentId === moment.momentId,
        );
        updatedMoments[index] = response.data.moment;
        await storeItem('moments', updatedMoments);
        setMoments(updatedMoments);
      }
    } catch (error) {
      console.error('Error updating moment:', error);
      showSnackbar('Error updating moment', 'error');
    }
  };

  const deleteMoment = async momentId => {
    try {
      const response = await axios.delete(`${BACKEND_URL}:30001/moments`, {
        data: {id: momentId},
      });
      if (response.status === 200) {
        let updatedMoments = (await retrieveItem('moments')) || [];
        updatedMoments = updatedMoments.filter(
          item => item.momentId !== momentId,
        );
        await storeItem('moments', updatedMoments);
        setMoments(updatedMoments);
      }
    } catch (error) {
      console.error('Error deleting moment:', error);
      showSnackbar('Error deleting moment', 'error');
    }
  };

  return {
    moments,
    isLoading,
    fetchMoments,
    addMoment,
    updateMoment,
    deleteMoment,
  };
};
