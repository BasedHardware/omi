import { Tx } from "../storage/inTx";

export async function getNextSeq(tx: Tx, uid: string) {
    let output = await tx.update.aggregate({ where: { userId: uid }, _max: { seq: true } });
    let seq = output._max.seq;
    if (seq === null) {
        seq = 0;
    }
    return seq + 1;
}

export async function getLastSeq(tx: Tx, uid: string) {
    let output = await tx.update.aggregate({ where: { userId: uid }, _max: { seq: true } });
    let seq = output._max.seq;
    if (seq === null) {
        seq = -1;
    }
    return seq;
}