import React, {useContext, useEffect} from 'react';
import {View, Text, StyleSheet, Animated} from 'react-native';
import {SnackbarContext} from '../contexts/SnackbarContext'; 

const MySnackBar = () => {
  const {snackbarInfo} = useContext(SnackbarContext);
  const {open, message, severity} = snackbarInfo;
  const opacity = new Animated.Value(0);

  useEffect(() => {
    if (open) {
      // Fade in
      Animated.timing(opacity, {
        toValue: 1,
        duration: 500,
        useNativeDriver: true,
      }).start();

      // Fade out after 6 seconds
      const timer = setTimeout(() => {
        Animated.timing(opacity, {
          toValue: 0,
          duration: 500,
          useNativeDriver: true,
        }).start();
      }, 6000);

      // Clear timeout if component unmounts
      return () => clearTimeout(timer);
    }
  }, [open, opacity]);

  const backgroundColor = severity === 'error' ? 'red' : 'green';

  return (
    <Animated.View style={[styles.snackbar, {opacity, backgroundColor}]}>
      <Text style={styles.text}>{message}</Text>
    </Animated.View>
  );
};

const styles = StyleSheet.create({
  snackbar: {
    position: 'absolute',
    bottom: 50,
    left: 0,
    right: 0,
    padding: 10,
    alignItems: 'center',
    justifyContent: 'center',
  },
  text: {
    color: 'white',
  },
});

export default MySnackBar;
