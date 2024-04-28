import {useEffect} from 'react';
import {View, Text, StyleSheet, Animated} from 'react-native';

const MySnackBar = ({open, message, severity}) => {
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
      setTimeout(() => {
        Animated.timing(opacity, {
          toValue: 0,
          duration: 500,
          useNativeDriver: true,
        }).start();
      }, 6000);
    }
  }, [open]);

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
