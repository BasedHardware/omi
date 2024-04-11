import { AsyncLock, InvalidateSync } from "teslabot";
import { SuperClient } from "../api/client";
import { backoff } from "../../utils/time";
import { Update, Updates } from "../api/schema";
import { storage } from "../../storage";
import { log } from "../../utils/logs";

export class UpdatesModel {
    readonly client: SuperClient;
    #seq: number | null = null;
    #sync: InvalidateSync;
    #lock = new AsyncLock();
    #queue = new Array<{ seq: number, update: Update | null }>();
    onUpdates?: (updates: Update) => Promise<void>;

    constructor(client: SuperClient) {
        this.client = client;
        let s = storage.getNumber('updates-seq');
        if (s !== undefined) {
            this.#seq = s;
        }
        this.#sync = new InvalidateSync(this.#doSync, { backoff });
    }

    start() {
        this.#sync.invalidate();
        setInterval(() => {
            this.#sync.invalidate();
        }, 10000);
        this.client.updates(this.#doReceive);
    }

    #doReceive = (seq: number, update: Update | null) => {
        if (!this.#seq) { // Not ready
            return;
        }
        if (seq > this.#seq) {
            this.#queue.push({ seq, update: update });
            this.#sync.invalidate();
        }
    }

    #doSync = async () => {
        await this.#lock.inLock(async () => {
            while (true) {
                if (this.#seq === null) {
                    this.#seq = await this.client.getUpdatesSeq();
                    storage.set('updates-seq', this.#seq);
                    log('UPD', 'Initial seq:' + this.#seq);
                } else {
                    // Process queue
                    if (this.#queue.length > 0) {

                        // Sort
                        this.#queue.sort((a, b) => a.seq - b.seq);

                        // Remove outdated
                        this.#queue = this.#queue.filter(item => item.seq > this.#seq!);

                        // Apply updates
                        while (this.#queue.length > 0 && this.#queue[0].seq === this.#seq + 1) {
                            let update = this.#queue.shift()!;
                            if (this.onUpdates && update.update !== null) {
                                await this.onUpdates(update.update);
                            }
                            this.#seq++;
                            storage.set('updates-seq', this.#seq);
                        }
                    }

                    let diff = await this.client.getUpdatesDiff(this.#seq);
                    log('UPD', 'Diff:' + diff.seq + ', hasMore:' + diff.hasMore + ', updates:' + diff.updates.length);

                    // Apply updates
                    if (this.onUpdates) {
                        for (let upd of diff.updates) {
                            let parsed = Updates.safeParse(upd);
                            if (parsed.success) {
                                await this.onUpdates(parsed.data);
                            } else {
                                log('UPD', 'Failed to parse update:' + JSON.stringify(upd));
                            }
                        }
                    }

                    // Update seq
                    if (this.#seq !== diff.seq) {
                        this.#seq = diff.seq;
                        storage.set('updates-seq', this.#seq);
                    }

                    // Nothing to do
                    if (!diff.hasMore) {
                        break;
                    }
                }
            }
        });
    }
}