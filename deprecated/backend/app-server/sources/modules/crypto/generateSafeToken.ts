import * as crypto from 'crypto';

export async function generateSafeToken() {
    return crypto.randomBytes(32).toString('hex');
}