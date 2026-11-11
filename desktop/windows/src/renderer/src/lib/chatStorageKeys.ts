// localStorage key for the shared 'infinite' chat conversation id. Kept in this
// leaf module (no React, no other app imports) so both useChat.ts and
// authTeardown.ts can import it without creating a cycle — authTeardown is
// imported by firebase.ts, and useChat.ts pulls in React/hooks that must never
// be reachable from that import chain.
export const CHAT_INFINITE_ID_KEY = 'omi-chat-infinite-id'
