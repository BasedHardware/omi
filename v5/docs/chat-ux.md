# Chat UX: wrapper cutover

## Decision

Desktop Chat is a stage destination beside Activity, Recall, and Settings. The top Ask control starts a conversation and navigates to Chat; the transcript is the only answer surface. A Chat control in the second row makes the destination available without composing first. Chat owns its bottom composer, while Search still goes to Recall. This matches the shipping Mac's persistent reading panel and removes the scrim and competing inline reply. Mobile Chat is a pushed page: Back returns to the previous page, the tab bar is absent, and its bottom composer shows only the Ask input. Search remains on the parent page. The same message history remains in the orchestrator as pages change.

## Before: audit

Severity is impact on comprehension or completing a chat turn. Evidence refers to the pre-change `_ux-final` screenshots and the named implementation files at the lane base (`f1567648`).

| Area | Severity | Evidence and problem |
| --- | --- | --- |
| Desktop entry/exit and mental model | High | `desktop-chat-light.png` shows a gray scrim over Activity, no Chat destination selected, and no close control inside the panel. `DesktopApp.tsx` `ChatOverlay` used an absolute fill and dismiss scrim. It read as a modal even though chat is an ongoing destination. |
| Two answer surfaces | High | `DesktopApp.tsx:539` (`InlineAskCard`) and `DesktopApp.tsx:591` (`ChatOverlay`) showed the same answer in clipped and full forms. Users had to decide where to read and continue. |
| Composer placement and focus | High | `desktop-chat-light.png` has the only composer in the top chrome, outside the transcript panel. Suggestions focused that omnibar. This breaks the conversation's spatial continuity. |
| Mobile entry/exit and mode | Medium | `mobile-ask-dark.png` has a back chevron, but `MobileChat.tsx` called it “Close chat”; `MobileOmnibar.tsx` kept Ask and Search mode icons in the conversation composer, and `MobileAppSurface.tsx` kept the tab bar on the pushed page. |
| History/continuity | Medium | `DesktopApp.tsx:591` and `MobileChat.tsx:148` rendered the shared `messages`, so route changes retained the conversation. Desktop's overlay and inline card obscured that continuity. Earlier history is explicit in `MobileChat.tsx:106` and `DesktopChat.tsx`'s scroll region. |
| Streaming/thinking/stop | Medium | `ChatTranscript.tsx` had skeleton rows and animated Omi mark; `desktop-chat-waiting-dark.png` and `mobile-ask-waiting-dark.png` show the state. The stop control was remote from the desktop transcript. Streaming text uses a plain `Text` until terminal Markdown so partial syntax does not thrash. |
| Retry and errors | Medium | `mobile-ask-error-light.png` shows a send error below the thread; failed assistant rows offer retry when the wire outcome is retryable. Desktop `DesktopChat.tsx` did not pass `onRetry` into `ChatMessageRow`, leaving a failed turn without its local recovery action. FC-CHAT-007 duplicate-on-retry remains a separate wire issue. |
| Scroll and long answers | Medium | `DesktopChat.tsx` measured scroll-away and `AppOrchestrator.tsx` tracked mobile following, but neither surfaced a jump control. `desktop-chat-light.png` shows the old top composer separated from the scroll region; `_ux-final` had no long-thread/code scenario to prove reachability. |
| Markdown, sources, copy, feedback | Medium | `ChatMessageContent.tsx:19` and `ChatMessageContent.tsx:46` rendered safe links/code, but native block edges used fixed gray (`:107`); `ChatTranscript.tsx:25` had no per-reply copy. The legacy chat message shape in `chatClient.ts` carries text/outcome, not structured citations or thumbs feedback; linked sources can render as links, but source cards/feedback need a separate contract. |
| Empty/prompts and appearance | Low | `desktop-chat-empty-light.png` and `mobile-ask-empty-dark.png` show prompts, though the desktop overlay separated them from the composer. Both surfaces use theme tokens for their main colors; visual audit must cover long/error states in both schemes. |
| Keyboard and accessibility | Medium | `MobileChat.tsx:69` labelled the pushed-page back control “Close chat”; `desktop-chat-light.png` shows the dismissible overlay that had no Esc path in `DesktopApp.tsx:591`. Message waiting/error states carried live/alert labels, but copy and jump controls were missing for keyboard and screen reader use. |

## Target and acceptance

- **Desktop:** Chat is a full stage panel with a reading column, right-aligned quiet user blocks, flat Omi replies, a bottom capsule composer, a visible Chat destination, and an Activity exit. Both the v5.1 filters layout and the older selectable v5 pages layout use that composer. Ask submission opens this stage immediately. Search opens Recall. Esc removes focus in Chat and returns from a deeper page to Chat; the host still owns window behavior. No chat UI issues window commands in `hostMode`.
- **Mobile:** Chat covers the content stage as a pushed page with Back and “Ask Omi” title; the tab bar and Ask/Search switch belong to the parent page. The composer stays below the scroll region. Back preserves the transcript; returning opens the same conversation.
- **Both:** Waiting and streaming are identifiable, Stop stays near the composer, failed assistant rows expose Try Again when retryable, and a send error retains the draft for another Send. Send/history errors do not masquerade as empty. Scroll-away exposes Jump to Latest; sending resumes follow. Markdown lists, code and safe links remain legible in light and dark. Omi replies have a per-message copy action (native phones use the system share sheet's Copy action until a phone clipboard port exists). Prompts populate an editable draft. Structured citations and thumbs remain outside this lane's legacy wire contract.

Visual review states: `desktop-chat-{empty,waiting,streaming,stopped,failed,error,long}` and `mobile-ask-{empty,waiting,streaming,stopped,failed,error,long}`, each in light and dark. The fixture never contacts a production host.
