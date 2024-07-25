require('dotenv').config();
import { startAgentWorker } from "./modules/agent/startAgentWorker";
import { startApi } from "./modules/api/startApi";
import { loadFiles, s3client } from "./modules/storage/files";
import { db } from "./modules/storage/storage";
import { startCombineWorker } from "./modules/tracking/startCombineWorker";
import { startExpireWorker } from "./modules/tracking/startExpireWorker";
import { log } from "./utils/log";
import { delay } from "./utils/time";

async function main() {

    //
    // Connect to the database
    //

    log('Connecting to DB...');
    await db.$connect();

    //
    // Connect to s3
    //

    await loadFiles();

    //
    // Starts workers
    //

    await startExpireWorker();
    await startCombineWorker();
    await startAgentWorker();

    //
    // Start API
    //

    await startApi();

    //
    // Ready
    //

    log('Ready');
    while (true) {
        await delay(10000);
    }
}

main().catch(async (e) => {
    console.error(e);
    await db.$disconnect()
    process.exit(1);
}).then(async () => {
    log('Disconnecting from DB...');
    await db.$disconnect();
});