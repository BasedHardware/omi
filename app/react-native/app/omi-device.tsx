/**
 * Route wrapper for the wearable pairing screen.
 *
 * Exists at the top level rather than inside (tabs) so it is a normal pushed
 * screen with its own back navigation, and is not gated on __DEV__ -- pairing a
 * device is something a real user does.
 */
export { default } from '@/screens/OmiDeviceScreen';
