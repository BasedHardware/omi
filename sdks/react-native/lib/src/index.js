/**
 * Omi SDK for React Native
 */
/**
 * Echo function that returns a greeting with the provided word
 * @param word - The word to echo back
 * @returns A greeting string with the provided word
 */
export const echo = (word) => {
    console.log('Omi SDK: Echo function called');
    return `Hello from Omi SDK! You said: ${word}`;
};
/**
 * Scan for Omi devices
 * @returns Promise that resolves to an array of Omi devices
 */
export function scanForDevices() {
    // This is a placeholder implementation
    // In a real implementation, this would use the native module to scan for devices
    return Promise.resolve([
        {
            id: 'demo-device-1',
            name: 'Omi Device',
            rssi: -65,
        },
    ]);
}
