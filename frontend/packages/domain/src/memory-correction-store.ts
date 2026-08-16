/**
 * The correction path for platform-generation Memories.
 *
 * David's 2026-08-16 ruling retires in-place memory editing. Users correct
 * Omi by adding a fact. That fact is a user-asserted STM note
 * (`POST /v1/stm-notes/ops`, `write_door: "http"`), fully trusted, never
 * filtered, and structured like everything else. It does not patch a
 * synthesized proposition — there is no such write on that wire.
 *
 * This store is SEPARATE from `SynthesizedMemoriesStore` on purpose. The
 * read model has no writes; pointing it at a create would satisfy a type
 * and lie about the projection. The correction port is named, and the
 * surface that wants it asks for it by name.
 */

import type { HttpClient } from "@omi-core/contracts";
import {
  observeAccountEpochFromTasksRead,
  sendUserAssertedStmNote,
  WRITE_ID_ENTROPY_BYTES,
  type MutableAccountEpochProvider,
  type WriteEntropySource,
} from "@omi-core/adapters-platform";

export class MemoryCorrectionStore {
  private constructor(
    private readonly http: HttpClient,
    private readonly epochs: MutableAccountEpochProvider,
    private readonly entropy: WriteEntropySource,
  ) {}

  static open(
    http: HttpClient,
    epochs: MutableAccountEpochProvider,
    entropy: WriteEntropySource,
  ): MemoryCorrectionStore {
    return new MemoryCorrectionStore(http, epochs, entropy);
  }

  /**
   * Submit a user-asserted fact. Does not mutate any existing synthesized
   * memory. Empty text is refused locally because there is nothing to seal;
   * the user's words are otherwise sent as written.
   */
  async submitFact(text: string): Promise<void> {
    const value = text.trim();
    if (value.length === 0) {
      throw new Error("refusing to submit an empty fact");
    }
    let epoch = this.epochs.currentAccountEpoch();
    if (epoch === null) {
      epoch = await observeAccountEpochFromTasksRead(this.http, this.epochs);
    }
    if (epoch === null) {
      throw new Error("refusing to stamp a fact without an account epoch");
    }
    let bytes: Uint8Array;
    try {
      bytes = this.entropy();
    } catch {
      throw new Error("refusing to submit a fact without write-id entropy");
    }
    if (!(bytes instanceof Uint8Array) || bytes.length !== WRITE_ID_ENTROPY_BYTES) {
      throw new Error("refusing to submit a fact without write-id entropy");
    }
    const result = await sendUserAssertedStmNote(this.http, {
      text: value,
      accountEpoch: epoch,
      entropy: bytes,
      clientWriteRef: null,
    });
    if (!result.ok) {
      throw new Error(`stm note write failed: ${result.failure.kind}`);
    }
  }
}
