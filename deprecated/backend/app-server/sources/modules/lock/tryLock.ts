import { db } from "../storage/storage";

async function readLock(key: string) {
    let ex = await db.globalLock.findUnique({ where: { key } });
    if (!ex) return null;
    return { value: ex.value, key: ex.key, timeout: ex.timeout };
}

async function trySetLock(key: string, value: string, expires: number, existing?: string) {
    if (existing) {
        if (value) {
            // Update if the existing value is the provided one
            await db.globalLock.update({ where: { key, value: existing }, data: { value, timeout: new Date(expires) } });
        } else {
            // Delete if the existing value is the provided one
            await db.globalLock.delete({ where: { key, value: existing } });
        }
    } else {
        if (value) {
            await db.globalLock.upsert({ where: { key }, update: { key, value, timeout: new Date(expires) }, create: { key, value, timeout: new Date(expires) } });
        } else {
            // Do nothing
        }
    }
}

export async function tryLock(lockKey: string, key: string, timeout: number) {
    while (true) {

        // Reading the lock
        let ex = await readLock(lockKey);
        if (!ex) {
            // Writing lock if it doesn't exist
            await trySetLock(lockKey, key, Date.now() + timeout);
            continue; // Retry
        }

        if (ex.value === key) {
            if (ex.timeout.getTime() < Date.now() - 10000) {  // If remaining time is less than 10 seconds, update the lock
                await trySetLock(lockKey, key, Date.now() + timeout, ex.value);
                continue; // Retry
            }

            // If key matches, update the lock
            await trySetLock(lockKey, key, Date.now() + timeout, ex.value);
            return true;
        } else {
            // If key do not match, check if the lock is expired
            if (ex.timeout.getTime() < Date.now()) {
                await trySetLock(lockKey, key, Date.now() + timeout, ex.value);
                continue;
            }
            return false;
        }
    }
}