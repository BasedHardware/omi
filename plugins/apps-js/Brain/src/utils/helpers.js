const crypto = require('crypto');

function handleDatabaseError(error, operation) {
    console.error(`Database error during ${operation}:`, error);
    return {
        status: 500,
        error: 'A database error occurred. Please try again later.'
    };
}

function decryptText(payload, keyB64) {
    try {
        if (!payload || typeof payload !== 'string' || !payload.includes(':')) return payload;

        const [ivB64, dataB64] = payload.split(':');
        if (!ivB64 || !dataB64) return payload;

        const iv = Buffer.from(ivB64, 'base64');
        const data = Buffer.from(dataB64, 'base64');
        const key = Buffer.from(keyB64, 'base64');
        const decipher = crypto.createDecipheriv('aes-256-gcm', key, iv);
        const ciphertext = data.slice(0, -16);
        const authTag = data.slice(-16);
        decipher.setAuthTag(authTag);
        const decrypted = Buffer.concat([decipher.update(ciphertext), decipher.final()]);
        return decrypted.toString('utf8');
    } catch {
        return payload;
    }
}

function getRandomElement(array) {
    return array[Math.floor(Math.random() * array.length)];
}

function resolveUid(req) {
    if (req.session?.userId) {
        return req.session.userId;
    }
    const rawUid = req.body?.uid || req.query?.uid;
    if (typeof rawUid === 'string' && rawUid.length >= 3 && rawUid.length <= 50) {
        return rawUid.replace(/[^a-zA-Z0-9-_]/g, '');
    }
    return null;
}

module.exports = {
    handleDatabaseError,
    decryptText,
    getRandomElement,
    resolveUid
};
