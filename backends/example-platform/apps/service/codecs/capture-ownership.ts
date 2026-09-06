import { createHash, createHmac, timingSafeEqual } from "node:crypto";
import { assertAuthorizedLedgerWriteContext, type AuthorizedLedgerWriteContext } from "../auth/authorized-context";

export interface CaptureOwnership {
  readonly ownerKey: string;
  readonly receipt: string;
}

export class CaptureOwnershipChanged extends Error {
  constructor() { super("capture_ownership_changed"); }
}

export function createCaptureOwnershipCodec(key: Uint8Array) {
  if (!(key instanceof Uint8Array) || key.byteLength < 32 || key.byteLength > 4096) throw new TypeError("invalid_capture_ownership_key");
  const secret = new Uint8Array(key);
  const ownerKey = (context: AuthorizedLedgerWriteContext) => {
    const authority = assertAuthorizedLedgerWriteContext(context);
    if (authority.capability !== "listen.capture.write") throw new TypeError("invalid_capture_ownership_authority");
    return `capture-owner-v1:${createHash("sha256").update(JSON.stringify(["omi.capture.owner.v1", authority.account_id, authority.account_epoch])).digest("hex")}`;
  };
  const signature = (owner: string) => createHmac("sha256", secret).update(`omi.capture.ownership-receipt.v1\0${owner}`).digest();
  return Object.freeze({
    issue(context: AuthorizedLedgerWriteContext): CaptureOwnership {
      const owner = ownerKey(context);
      return Object.freeze({ ownerKey: owner, receipt: `capture1.${owner.slice("capture-owner-v1:".length)}.${signature(owner).toString("hex")}` });
    },
    verify(context: AuthorizedLedgerWriteContext, receipt: string | null): void {
      const match = typeof receipt === "string" ? /^capture1\.([a-f0-9]{64})\.([a-f0-9]{64})$/.exec(receipt) : null;
      if (match === null) throw new TypeError("invalid_capture_ownership_receipt");
      const owner = `capture-owner-v1:${match[1]}`;
      if (!timingSafeEqual(signature(owner), Buffer.from(match[2]!, "hex"))) throw new TypeError("invalid_capture_ownership_receipt");
      if (owner !== ownerKey(context)) throw new CaptureOwnershipChanged();
    },
  });
}
