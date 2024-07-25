import * as crypto from 'crypto';

export async function deriveSeed(src: Buffer) {
    return crypto.createHmac('sha256', Buffer.from('Whales Phone Auth Seed')).update(src).digest();
}