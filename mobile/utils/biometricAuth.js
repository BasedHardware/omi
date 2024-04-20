import * as LocalAuthentication from 'expo-local-authentication';

const biometricAuth = async () => {
  const compatible = await LocalAuthentication.hasHardwareAsync();
  if (!compatible) {
    throw new Error('Your device is not compatible with biometric authentication');
  }

  const savedBiometrics = await LocalAuthentication.isEnrolledAsync();
  if (!savedBiometrics) {
    throw new Error('No biometrics found. Please set up biometric authentication in your device settings.');
  }

  const { success, error } = await LocalAuthentication.authenticateAsync({
    promptMessage: 'Authenticate',
    fallbackLabel: 'Enter Password', // This is used to show an alternative option to the user
  });

  if (success) {
    console.log('Authentication successful!');
    // Proceed with the app's flow
  } else {
    console.error('Authentication failed:', error);
    // Handle authentication failure or fallback to password
  }
};

const checkBiometricSupport = async () => {
  const isCompatible = await LocalAuthentication.hasHardwareAsync();
  if (!isCompatible) {
    console.log('Biometric authentication is not supported on this device.');
    return false;
  }

  const hasBiometrics = await LocalAuthentication.isEnrolledAsync();
  if (!hasBiometrics) {
    console.log('No biometrics found. Please set it up.');
    return false;
  }

  return true; // Device supports and is enrolled with biometrics
};

const promptBiometricAuth = async () => {
  const { success, error } = await LocalAuthentication.authenticateAsync({
    promptMessage: 'Confirm your identity',
    fallbackLabel: 'Use your passcode', // Provide an alternative for devices that support it
  });

  if (success) {
    console.log('Biometric authentication successful.');
    return true;
  } else {
    console.error('Biometric authentication failed', error);
    return false;
  }
};