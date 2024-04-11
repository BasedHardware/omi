import { delay } from "../../utils/time";
import { runInLock } from "../lock/runInLock";
import { expireSessions } from "./session";

export async function startExpireWorker() {
    runInLock('expire-worker', async () => {
        console.log('Running expire worker');
        let expired = await expireSessions();
        if (expired > 0) {
            console.log(`Expired ${expired} sessions`);
        }
        await delay(5000);
    });
}