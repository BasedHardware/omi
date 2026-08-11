/**
 * Public service facade for already-issued ledger write authority.
 *
 * Minting lives in `authorized-context-internal.ts`, whose imports are fenced to
 * this facade, tests, and a future single reviewed auth composition. Ordinary
 * application and driver modules can validate or carry authority, never mint it.
 */
export {
  assertAuthorizedLedgerWriteContext,
  assertAuthorizedLedgerWriteContextCurrentAt,
  AUTHORIZED_LEDGER_CONTEXT_VERSION,
} from "./authorized-context-internal";
export type {
  AuthorizedLedgerWriteContext,
} from "./authorized-context-internal";
