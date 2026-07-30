/** T10 boundary only: retrieval/omission accounting are intentionally unimplemented in M-skeleton T0-T7. */
export interface RetrievalPort { retrieve(request: unknown): Promise<unknown>; }
export interface ProvisionalInclusionPolicy { include_provisional: boolean; }
