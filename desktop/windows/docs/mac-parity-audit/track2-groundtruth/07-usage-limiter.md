# Ground truth: Bar usage-limiter / paywall (Track 2)

**IMPORTANT correction to the brief's premise:** `effective_desktop_access_tier` and
the tier enum `desktop_free` / `desktop_full` / `desktop_architect` **do not exist
anywhere in this codebase** — not in Mac, not in Windows `lib/billing.ts`, not in the
backend. I grepped the full repo (backend, mac-ref, track2-voice-bar) for that exact
string and for the three tier tokens; zero hits. The real backend contract (both Mac
and Windows consume it) is `ChatUsageQuota.plan_type: 'basic' | 'unlimited' | 'architect' | 'operator'`
(`backend/models/users.py:15-26,49-57`) plus a separate `allowed: bool` boolean —
i.e. the gate you need to build IS effectively a binary "allowed" check on the
`/v1/users/me/usage-quota` response, gated by `plan_type` only for display/copy
purposes, not for the block decision itself. See §4 below for the full contract.
Everything else in the brief is accurate and extracted below.

---

## 1. Mac limiter behavior (FloatingBarUsageLimiter.swift)

File: `desktop/macos/Desktop/Sources/FloatingControlBar/FloatingBarUsageLimiter.swift`

- Singleton `FloatingBarUsageLimiter.shared`, shared between the floating bar (typed
  + PTT) and the main chat page (`ChatProvider.sendMessage`) — one quota pool
  (line 3-7).
- State: `serverQuota: APIClient.ChatUsageQuota?` (last server snapshot) +
  `optimisticDelta: Int` (queries sent locally since last sync) (lines 16-19).
- **`isLimitReached` (lines 77-96):**
  1. `if APIKeyService.isByokActive { return false }` — BYOK users are **never**
     limited, checked first, client-side (line 81-83).
  2. `guard let quota = serverQuota else { return false }` — fail-open when no
     quota snapshot yet (server will enforce) (line 84-87).
  3. `if quota.allowed { guard quota.unit == "questions", let limit = quota.limit
     else { return false }; return (quota.used + Double(optimisticDelta)) >= limit }`
     — for `cost_usd` units (Architect/Pro) there's no local cost estimate, so it
     trusts the server snapshot alone and returns `false` (not reached) (lines 88-94).
  4. `return true` — if `quota.allowed == false` server-side, always blocked
     regardless of unit (line 95).
- **`limitDescription` (lines 105-113):** `"your monthly free message limit"`
  (no quota yet) / `"your $N <plan> monthly spend limit"` for `cost_usd` /
  `"<N> <plan> messages this month"` for `questions`.
- **`recordQuery()` (line 117-119):** `optimisticDelta += 1` — called AFTER a
  successful send, from both the floating bar and main chat.
- **Refresh cadence — no periodic timer.** `fetchPlan()` (→ `syncQuota()`) is
  called on: app launch (`OmiApp.swift:1476`), every auth state change (sign-in,
  token refresh, sign-out ×5 call sites in `AuthService.swift`), after
  BYOK/API-key settings changes (`SettingsContentView+DeveloperKeys.swift`), after
  checkout completes (`ChatProvider.swift:2666`), and settings page appear
  (`SettingsPage.swift:564`). Additionally, **lazily right before every floating-bar
  query** if `serverQuota == nil` (cold-start/network-blip guard), forcing one
  `syncQuota()` round trip before the limit check
  (`FloatingControlBarWindow.swift:4239-4256`).

### Exact verbatim copy — two DIFFERENT strings for two DIFFERENT surfaces

1. **Inline local assistant message** in the bar's own chat stream (typed path),
   `FloatingControlBarWindow.swift:4262-4265`:
   > `"You've reached \(limiter.limitDescription). Upgrade to keep chatting without restrictions."`

   Same string spoken via TTS for the voice/PTT path,
   `FloatingControlBarWindow.swift:4453-4455`:
   > `"You've reached \(limiter.limitDescription). Upgrade to keep chatting without restrictions."`

   Main-chat-page variant (slightly different, no `limitDescription` interpolation
   trailing punctuation match — verify against source, not memory) is
   `ChatProvider.swift:3783`:
   > `"You've reached \(usageLimiter.limitDescription). Upgrade to keep chatting."`

2. **Modal popup body** (`UsageLimitPopupView.swift`, rendered as an `.overlay` on
   `DesktopHomeView.mainContent` — the MAIN WINDOW, not the bar itself), reason
   `"chat"` or `"floating_bar"` (both map to the same copy),
   `UsageLimitPopupView.swift:24-25`:
   > `"You've hit your monthly limit. Upgrade to keep chatting with Omi without restrictions."`

   Headline (all reasons): `"You've hit your monthly limit"` (line 17). Buttons:
   `"Upgrade"` (navigates to Settings → Plan & Usage) and `"Bring your own keys"`
   (navigates to Settings → Advanced) — `UsageLimitPopupView.swift:87-107`.

### Trigger points (both typed AND PTT gated — confirmed)

| Surface | Gate location | What happens |
|---|---|---|
| Typed bar query | `FloatingControlBarWindow.swift:4257-4273` | Pre-send check inside the async send pipeline, AFTER `prepareVisibleQueryState` (message already optimistically shown) but BEFORE `provider.sendMessage`/`limiter.recordQuery()`. Sets a local-only `ChatMessage` override + posts `.showUsageLimitPopup` reason `"floating_bar"`. |
| Voice/PTT bar query (post-transcription) | `FloatingControlBarWindow.swift:4448-4459` | Same pre-send position in the voice-query pipeline; speaks the message via TTS instead of rendering a bubble; does NOT post a popup notification here (only the two `isBlockedByUsageLimit()` sites below do). |
| PTT hold-to-start (BEFORE recording begins) | `PushToTalkManager.swift:409-415`, called from `startListening()` (line 422) and `enterLockedListening()` (line 466) | Blocks the PTT gesture itself — mic never opens — and posts `.showUsageLimitPopup` reason `"ptt"`. This is an EARLIER, cheaper gate than the post-transcription one above; comment at 404-408 explains it exists so "a free user over 30 questions could keep talking for free" isn't possible even before STT runs. |
| Main chat page | `ChatProvider.swift:3778-3788` | Same `isLimitReached` check, reason `"chat"`. |

So Mac has **two layers of PTT gating**: an early block on the hold gesture itself
(mic never opens) AND a second check after transcription completes but before the
LLM call (belt-and-suspenders against a race where the limit ticks over mid-hold).

### `.showUsageLimitPopup` notification

`NotificationCenter` name, posted with `userInfo: ["reason": <string>]` from 4 call
sites (`floating_bar`, `ptt`, `chat`, `trial_expired`). Consumed once, in
`DesktopHomeView.swift:166-169`:
```swift
.onReceive(NotificationCenter.default.publisher(for: .showUsageLimitPopup)) { notification in
  let reason = notification.userInfo?["reason"] as? String ?? ""
  appState.triggerUsageLimitPopup(reason: reason)
}
```
This drives `appState.showUsageLimitPopup` / `appState.usageLimitReason`, which
renders `UsageLimitPopupView` as an overlay on `DesktopHomeView.mainContent`
(`DesktopHomeView.swift:130-165`) — i.e. **the popup always shows on the MAIN
window**, even when triggered from the floating bar or PTT. The bar itself only
shows the inline local message / speaks the TTS line; it relies on the main window
being visible (or becoming visible) to show the modal upsell.

### BYOK exemption

Confirmed non-BYOK only: `FloatingBarUsageLimiter.isLimitReached` line 81-83
checks `APIKeyService.isByokActive` FIRST and short-circuits `false` (never
limited) for BYOK. This is a CLIENT-side check on Mac. Separately, the BACKEND
also exempts BYOK server-side at the quota-fetch level (see §4) — Mac's client
check is a fast-path/redundant safety net on top of an already-exempting server
response.

---

## 2. Windows `lib/usageLimit.ts` — exact public API (CONSUME, do not rebuild)

File: `desktop/windows/src/renderer/src/lib/usageLimit.ts`

```ts
export type UsageLimitReason = 'chat' | 'transcription' | 'trial_expired'

export function onUsageLimit(cb: (reason: UsageLimitReason | null) => void): () => void
export function showUsageLimit(reason: UsageLimitReason): void
export function dismissUsageLimit(): void
export function __resetUsageLimitSession(): void   // test-only

export async function maybeTriggerChatQuotaPopup(
  fetchQuota: () => Promise<ChatUsageQuota>
): Promise<boolean>
```

**Critical behavioral note — this is NOT a pre-send gate.** `maybeTriggerChatQuotaPopup`
is a *reactive, post-send* probe: call it any time after a send settles; it does a
cheap `fetchQuota()` GET and, if `quota.allowed === false`, calls `showUsageLimit('chat')`.
It self-guards to fire **at most once per app session** (`chatQuotaPopupShown` module
flag, reset only via `__resetUsageLimitSession()` in tests) — comment at lines 23-27
explicitly says this exists because "the chat send path lives on another branch, so
rather than rewire it we watch the quota from the outside." There is **no reason
value `'floating_bar'` or `'ptt'`** in `UsageLimitReason` — only `'chat' | 'transcription'
| 'trial_expired'`. If Track 2 wants bar-specific reason text it must either reuse
`'chat'` or extend the union type (extending it is a shared-file edit — coordinate,
don't unilaterally change the type since `UsageLimitPopup.tsx`'s `BODY` record is
keyed off it exhaustively).

`onUsageLimit`/`showUsageLimit`/`dismissUsageLimit` are a **global signal channel**
(`createSignal` from `./signal`) — any code anywhere in the renderer can call
`showUsageLimit(reason)` directly to raise the popup; you do NOT have to go through
`maybeTriggerChatQuotaPopup`. This is the reusable primitive for a bar-owned
pre-send gate: call `showUsageLimit('chat')` yourself once you've independently
determined the quota is exhausted.

**Caveat — signal is process/module-global, not necessarily cross-window.** The bar
(`#/bar`) is a separate Electron renderer process from the main window (confirmed:
`BarApp.tsx` header comment "this renderer holds NO useChat" + everything goes over
`window.omiBar.*` IPC). `createSignal` (`lib/signal.ts`) is in-memory JS state —
it does NOT cross an Electron `BrowserWindow` process boundary. Calling
`showUsageLimit()` from the bar's renderer will only notify subscribers *in the bar's
own renderer*; `UsageLimitPopup.tsx` (which renders the actual modal) is currently
mounted only in the main-window app root (confirmed by `UsageLimitTriggerHost.tsx`
doc comment: "Mounted once at the app root, main window only"). **This means calling
`showUsageLimit()` from bar code today shows nothing** unless a `UsageLimitPopup`
instance is also mounted inside the bar's own renderer tree, or the bar forwards the
trigger to the main window over IPC. See §3 for the seam recommendation.

## `lib/billing.ts` — exact public API relevant to the gate (CONSUME)

File: `desktop/windows/src/renderer/src/lib/billing.ts`

```ts
export function fetchChatQuota(): Promise<ChatUsageQuota>   // GET /v1/users/me/usage-quota, line 34-36
export const QUOTA_WARNING_PERCENT = 80
export type QuotaView = {
  valueText: string; description: string; fraction: number; percent: number;
  allowed: boolean; resetAt: number | null; warning: boolean; belowBarWarning: string
}
export function chatQuotaView(quota: ChatUsageQuota, isOveragePlan?: boolean): QuotaView
export function quotaResetText(resetAtSeconds: number | null, now?: Date): string
```

`chatQuotaView` is a **Settings-page (Plan & Usage tab) view model**, not
bar-specific — its `belowBarWarning` copy ("You've reached this month's limit.
Upgrade your plan or wait until the next reset." at line 275, or the overage
variant at line 273-274) is DIFFERENT wording from both Mac strings above and from
`UsageLimitPopup.tsx`'s `BODY.chat` string. Do not reuse `chatQuotaView`'s copy for
the bar gate — it belongs to the usage progress-bar widget on the billing settings
page. For the bar you want raw `fetchChatQuota()` (the data) plus your own
copy/placement, or `UsageLimitPopup.tsx`'s existing `BODY.chat` string if you route
through the shared popup (see §3).

**No BYOK concept exists anywhere in `billing.ts` or `usageLimit.ts`.**
`UsageLimitPopup.tsx` line 9 states explicitly: *"Windows has no BYOK UI"* — its
"Bring your own keys" button (present on Mac) is omitted entirely. `ChatUsageQuota`
itself doesn't need a client-side BYOK branch because the **backend already returns
an unlimited/`allowed: true` quota for BYOK users** (see §4) — so `fetchChatQuota()`
naturally reports "not limited" for BYOK accounts without any Windows-side BYOK
check. Track 2 does not need to special-case BYOK at all; trust `quota.allowed`.

### `main/billing/**` IPC surface

File: `desktop/windows/src/main/billing/checkoutWindow.ts` — only two IPC handlers,
both checkout/portal, **nothing quota-related**:
```ts
ipcMain.handle('billing:openCheckout', (_e, url: string) => openCheckoutWindow(String(url)))
ipcMain.handle('billing:openExternal', (_e, url: string) => ...)  // system browser, portal only
```
There is no main-process quota cache, no main→renderer quota push, and no
existing IPC channel for "show usage limit popup" cross-window. `fetchChatQuota()`
is called directly from renderer code via the (already-authenticated) `omiApi`
axios client — no main-process involvement needed to read quota. If you need the
popup to appear on the MAIN window when triggered from the BAR window, you will
need to add a new IPC channel (e.g. via the existing `omiBar`/`omiOverlay` preload
bridges) — none currently exists for this purpose.

---

## 3. Cleanest seam in files you OWN (bar gate, typed + PTT, no `useChat.ts` edit)

**Single choke point: `sendFromBar` in `components/bar/BarApp.tsx:116-121`.**

```ts
const sendFromBar = useCallback((text: string, fromVoice: boolean): void => {
  if (!text.trim()) return
  window.omiOverlay.notifyAsked()
  window.omiBar.sendChat(text, fromVoice)
}, [])
```

Both send paths already funnel through this one function:
- Typed: `BarChatSurface`'s `onSubmit={(text) => sendFromBar(text, false)}` (`BarApp.tsx:377`)
- PTT: `usePushToTalk({ onCommit: (text) => sendFromBar(text, true), ... })` (`BarApp.tsx:139`)

This is the correct and ONLY place to add a pre-send gate for both typed and PTT —
it requires editing only `BarApp.tsx` (a file you own), not `useChat.ts` (Track-1-owned,
not even touched by the bar renderer per its own header comment) and not
`usePushToTalk.ts`/`AskPanel`-equivalent (`BarChatSurface.tsx`).

**Recommended shape** (illustrative, not prescriptive — actual UI/copy decisions are
yours):

```ts
const sendFromBar = useCallback((text: string, fromVoice: boolean): void => {
  if (!text.trim()) return
  if (quotaExhausted) {           // derived from a fetchChatQuota() poll/cache you own
    // show your own in-bar limit UI (Mac-parity: inline message + optional TTS)
    // AND/OR forward an IPC signal to the main window to raise the shared modal
    return
  }
  window.omiOverlay.notifyAsked()
  window.omiBar.sendChat(text, fromVoice)
}, [quotaExhausted])
```

**Open design question this ground-truth surfaces (yours to decide, not a blocker):**
Mac's PTT gate blocks the mic from opening at all (`PushToTalkManager.isBlockedByUsageLimit`,
called from `startListening()`/`enterLockedListening()` BEFORE any capture starts).
The Windows equivalent hook point for that earlier gate would be inside
`usePushToTalk`'s `onCommit`-adjacent flow, but `usePushToTalk.ts` doesn't expose a
pre-capture veto hook — its `beginHold`/`gestureDown` start the mic unconditionally.
Since `usePushToTalk.ts` is presumably also outside your edit scope (it's not
`components/bar/**` or `lib/ptt/**` per your brief's "files I own" list — it's
`hooks/usePushToTalk.ts`), the earliest gate you can cleanly add without touching
files outside your scope is at `onCommit` in `BarApp.tsx:139` (i.e. gate
`sendFromBar`, same as typed) — this matches Mac's SECOND, post-transcription gate
but not its FIRST, pre-mic-open gate. If you want Mac's earlier gate too, that
requires either (a) editing `usePushToTalk.ts` to accept an `isBlocked: () => boolean`
callback checked in `gestureDown`/`beginHold`, or (b) accepting the gap since Mac's
second gate already prevents any spend — recommend flagging this tradeoff back to
whoever owns `usePushToTalk.ts` rather than silently choosing.

**For the actual popup/message UI**, three options, in order of parity vs. effort:
1. **Lowest effort, breaks cross-window parity**: call `showUsageLimit('chat')`
   from `BarApp.tsx` and ALSO mount a `<UsageLimitPopup />` instance inside the bar's
   own render tree (it's a self-contained component reading `onUsageLimit`) — shows
   the modal-in-bar instead of modal-on-main-window. Reuses 100% of existing markup
   and copy (`UsageLimitPopup.tsx`'s `BODY.chat` string), zero new IPC.
2. **Mac parity**: add a lightweight IPC channel (`window.omiBar.showUsageLimitInMain()`
   or similar, main-process relay) so the bar can raise the popup on the MAIN window
   like Mac does, keeping the bar itself showing only an inline message (Mac-parity
   local `ChatMessage` override / TTS line). Requires a new preload/IPC addition —
   still confined to files you'd own (`components/bar/**`, plus a new small IPC file
   if that counts as yours; otherwise coordinate for the preload surface).
3. **Bar-native inline message**, no popup at all — inject a local assistant-style
   message into the bar's own `chat.messages` render (mirrors Mac's
   `setLocalAnswerOverride` local-only bubble) using Mac's exact copy
   `"You've reached {limitDescription}. Upgrade to keep chatting without restrictions."`
   This needs a `limitDescription`-equivalent formatter — none exists in `billing.ts`
   today; you'd derive it from `ChatUsageQuota.unit`/`limit`/`plan` yourself (a few
   lines, same logic as Mac's `limitDescription` getter, §1).

None of these require editing `useChat.ts`.

---

## 4. `/v1/users/me/usage-quota` contract + tier semantics

Endpoint: `backend/routers/users.py:1264-1305` (approx).

```python
@router.get('/v1/users/me/usage-quota', tags=['users'], response_model=ChatUsageQuota)
def get_user_chat_usage_quota(
    uid: str = Depends(auth.get_current_user_uid),
    x_app_platform: Optional[str] = Header(None, alias='X-App-Platform'),
):
    if users_db.is_byok_active(uid) and has_byok_keys():
        return ChatUsageQuota(
            plan='Free (BYOK)', plan_type=PlanType.unlimited.value,
            unit=ChatQuotaUnit.questions, used=0.0, limit=None,
            percent=0.0, allowed=True, reset_at=None,
        )
    snapshot = get_chat_quota_snapshot(uid, platform=x_app_platform)
    ...
    return ChatUsageQuota(
        plan=get_plan_display_name(plan), plan_type=plan.value,
        unit=ChatQuotaUnit(snapshot['unit']), used=round(snapshot['used'], 4),
        limit=snapshot['limit'], percent=percent,
        allowed=snapshot['allowed'], reset_at=snapshot['reset_at'],
    )
```

**Server-side BYOK exemption is unconditional and precedes everything else**
(`users.py:1276-1286`) — `allowed: True`, `limit: None` (unlimited), regardless of
platform. Windows never needs its own BYOK branch (see §2).

Response model (`backend/models/users.py:49-57`):
```python
class ChatUsageQuota(BaseModel):
    plan: str              # display name: "Free", "Neo", "Operator", "Architect", "Free (BYOK)"
    plan_type: str          # internal id: "basic" | "unlimited" | "architect" | "operator"
    unit: ChatQuotaUnit      # "questions" | "cost_usd"
    used: float
    limit: Optional[float] = None   # None = unlimited
    percent: float = 0.0
    allowed: bool = True    # <-- THE block/allow decision, computed server-side
    reset_at: Optional[int] = None  # unix seconds, start of next UTC month
```

`PlanType` enum (`models/users.py:15-26`): `basic` ("Free"), `unlimited` (LEGACY
display "Unlimited"/"Neo"), `architect` (also matches legacy `'pro'` via
`_missing_`), `operator`. **No `desktop_free`/`desktop_full`/`desktop_architect`
values exist** — confirms the §0 correction.

**"Reached" is computed entirely server-side** inside `get_chat_quota_snapshot`
(`utils/subscription.py:605+`) — the client (`allowed` field) just reads the
verdict; there is no client-side threshold math needed beyond what Mac already does
optimistically (`optimisticDelta`) as a latency hedge between sends and quota
refreshes. `unit` distinguishes two cap shapes: `questions` (Neo/Operator — a raw
count vs `limit`) vs `cost_usd` (Architect/Pro — a dollar spend cap; Mac deliberately
does NOT try to estimate this client-side, per §1).

**Windows platform recognition — confirmed correct, no legacy-catalog trap here.**
`backend/utils/subscription.py:119`: `DESKTOP_PLATFORMS = {'macos', 'windows'}` —
single source of truth for "is this a desktop platform," used by
`get_chat_quota_snapshot`'s `platform` param (paywall-test-override gating) and by
`filter_plans_for_user`/`should_show_new_plans` elsewhere. `'windows'` is fully
recognized; the legacy-catalog canary documented in `billing.ts:46-56` is about a
DIFFERENT endpoint (`/v1/users/me/subscription`'s plan catalog), not this one — but
it's worth knowing both endpoints correctly recognize `windows` today (per
`billing.ts`'s own canary never having fired in this worktree, and per this grep of
`DESKTOP_PLATFORMS`).

TypeScript type (already generated, `lib/omiApi.generated.ts:712-721`):
```ts
export interface ChatUsageQuota {
  allowed?: boolean; limit?: number | null; percent?: number;
  plan: string; plan_type: string; reset_at?: number | null;
  unit: ChatQuotaUnit; used: number;
}
```
