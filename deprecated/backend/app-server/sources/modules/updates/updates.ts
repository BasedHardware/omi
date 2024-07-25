import { Tx, afterTx } from "../storage/inTx";
import { eventBus } from "./eventbus";
import { getNextSeq } from "./seq";
import { UpdateType } from "./updates.types";

export async function pushUpdate(tx: Tx, uid: string, update: UpdateType) {

    // Resolve next sequence number
    let seq = await getNextSeq(tx, uid);

    // Create update
    await tx.update.create({
        data: {
            userId: uid,
            seq: seq,
            data: update
        }
    });

    // Notify user
    afterTx(tx, () => {
        eventBus.emit(`update:${uid}`, seq, update);
    });
}

export async function getUpdates(tx: Tx, uid: string, after: number) {
    let updates = await tx.update.findMany({
        where: {
            userId: uid,
            seq: { gt: after }
        },
        orderBy: [{
            seq: 'asc'
        }],
        take: 101
    });

    let hasMore = updates.length === 101;
    if (hasMore) {
        updates.pop();
    }

    return { hasMore, updates };
}