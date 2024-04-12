import * as Crypto from 'expo-crypto';

export function randomKey() {
    let data = Crypto.getRandomBytes(32);
    return data.reduce((acc, byte) => acc + byte.toString(16).padStart(2, '0'), '');
}