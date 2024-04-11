import { Axios } from "axios";
import { backoff } from "../../utils/time";
import { Schema, Update, Updates, sseUpdate } from "./schema";
import { sse } from "./sse";

export class SuperClient {

    readonly client: Axios
    readonly token: string;

    constructor(client: Axios, token: string) {
        this.client = client;
        this.token = token;
    }

    fetchPreState() {
        return backoff(async () => {
            let res = await this.client.get('/pre/state');
            return Schema.preState.parse(res.data);
        })
    }

    preUsername(username: string) {
        return backoff(async () => {
            let res = await this.client.post('/pre/username', { username });
            return Schema.preUsername.parse(res.data);
        })
    }

    preName(firstName: string, lastName: string | null) {
        return backoff(async () => {
            let res = await this.client.post('/pre/name', { firstName, lastName });
            return Schema.preName.parse(res.data);
        })
    }

    preComplete() {
        return backoff(async () => {
            await this.client.post('/pre/complete');
        })
    }

    //
    // Session Operations
    //

    startSession(repeatKey: string) {
        return backoff(async () => {
            let res = await this.client.post('/app/session/start', { repeatKey, timeout: 45 }); // 15 seconds timeout
            return Schema.sessionStart.parse(res.data).session;
        })
    }

    async stopSession(session: string) {
        await this.client.post('/app/session/stop', { session });
    }

    uploadAudio(session: string, repeatKey: string, format: string, chunks: string[]) {
        return backoff(async () => {
            let res = await this.client.post('/app/session/upload/audio', { session, repeatKey, format, chunks });
            return Schema.uploadAudio.parse(res.data);
        });
    }

    //
    // List Sessions
    //

    listSessions() {
        return backoff(async () => {
            let res = await this.client.post('/app/session/list', {});
            return Schema.listSessions.parse(res.data);
        });
    }

    getFullSession(id: string) {
        return backoff(async () => {
            let res = await this.client.post('/app/session/get', { id });
            return Schema.getSession.parse(res.data);
        });
    }

    //
    // Updates
    //

    async getUpdatesSeq() {
        let res = await this.client.post('/app/updates/seq', {});
        return Schema.getSeq.parse(res.data).seq;
    }

    async getUpdatesDiff(seq: number) {
        let res = await this.client.post('/app/updates/diff', { after: seq });
        return Schema.getDiff.parse(res.data);
    }

    updates(handler: (seq: number, update: Update | null) => void) {
        return sse('https://super-server.korshakov.org/app/updates', this.token, (update) => {
            let parsed = sseUpdate.safeParse(JSON.parse(update));
            if (!parsed.success) {
                return;
            }
            let parsedUpdate = Updates.safeParse(parsed.data.data);
            if (parsedUpdate.success) {
                handler(parsed.data.seq, parsedUpdate.data);
            } else {
                console.error('Failed to parse update:', JSON.parse(update));
                handler(parsed.data.seq, null);
            }
        });
    }
}