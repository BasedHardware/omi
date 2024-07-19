import { startAuth } from "./operations";

describe('twilio', () => {
    xit('should validate number', async () => {
        await startAuth(process.env.TEST_PHONE_NUMBER!, 'key-1');
    });
});