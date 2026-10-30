# Structure: where things live

The Flutter app had every capability, but buttons everywhere and settings in odd places. The native
app keeps every capability (docs/PARITY.md) and puts each one in exactly one place a person would look.

## Rules
1. **One place per thing.** A setting or action lives in one screen; other places link there, they
   do not repeat it.
2. **Grouped by what people think about, not by implementation.** "Appearance" is not a kind of
   notification; "export my data" belongs with privacy, not with the account plan.
3. **Primary action visible, the rest in one menu.** A screen shows at most one or two buttons;
   everything else goes into its single "…" menu, context menu or swipe. No rows of icon buttons.
4. **Short screens.** A settings screen has at most four sections; anything longer is split into a
   pushed screen with a clear name.
5. **Home shows what matters now, then the day.** "Needs you": at most five decision cards, then
   "Later (n)" folded and a quiet "All tasks (n)" row, then conversations by day. Every card's tap
   opens something (`HomeTapTargets`); nothing is a dead tap.
6. **Rare things are reachable, not visible.** Developer options, imports, referral: one row deep
   inside the screen they belong to, never on Home or at the top of Settings.
7. **One-line, quiet rows in rounded groups.** As in the ChatGPT app's settings: each section is one
   rounded group in the raised card color on the plain page, rows divided by hairlines, a small gray
   section label above. A row is a thin gray line glyph, a short name and at most its current value
   on the right; no gray subtitle under every row and no colored icon tiles. Explanations go in a
   section footer, once. The Settings root and My Omi are the exception: their rows sit flat on the
   page (`OmiFlatList`), hairlines from the title to the edge, no card behind them.
8. **Advanced is one row.** Settings only some people need (speech model, on-device transcription,
   logs) sit in one pushed "Advanced" screen of the topic, not between the everyday ones.

## Settings tree
The root is a hub: the profile on top, four live tiles, then one flat list. Search sits behind the
magnifier in the top bar (the same index as before); `-omiSettingsTopic` deep links still open any
screen directly.
```
[Profile header]  name large, email · plan pill, Upgrade on the free plan (opens Plan & usage);
                  the avatar shows the name's initials (the email's first letter without a name).
                  The name comes from the backend (`GET v1/users/profile`), else this iPhone's
                  saved name. Tapping the header opens Account.
[Tiles, 2x2]      Omi (pendant, dot, "76% · Listening" / Not connected / Get an Omi) → My Omi
                  Plan (plan name, the most used limit as a thin meter and %) → Plan & usage
                  Apps ("3 connected": calendar, mail, task apps, Apple Health, Reminders) → Apps
                  Voices ("5 people") → Voices & people
Listening · Memory · Assistant · Notifications · Privacy & data · Appearance · Connect your AI · Help
More              Phone calls, Developer (only when developer mode is on), the app version

Account           name · email · plan & usage · invite friends · set up again · sign out · delete account
  Plan & usage    your plan (renews / ends on), this month (listening, chat, words, insights
                  against the limits), upgrade or change plan (Monthly / Yearly, one card per
                  plan, promo code, one button: Stripe's page in the app), payment method and
                  invoices, cancel subscription, what Omi heard (period, chart, share), fair use.
                  Every Upgrade button in the app opens this screen.
  Invite friends  one line, your link (share, copy), how it works

My Omi            (also the device pill on Home) laid out like AirPods in iOS Settings: the pendant
                  large in the middle (faded while away), its name, the status line (dot: red
                  listening, green connected, gray away; battery). Three round quick buttons: Pause
                  or Resume listening (filled while paused), Find (plays the Omi's sound), Light
                  (a small sheet with the brightness slider; the value under the label). Flat rows:
                  Microphone (Quiet / Normal / Loud), Press twice (menu), Use the button (toggle),
                  Recordings on your Omi (count; opens the sync line, storage and the recordings).
                  Then Software, About this Omi (model, firmware, codec, serial, connection health,
                  forget), Help with your Omi (learn the button, charging help). Away: the same
                  page, a Connect button under the status, quick buttons dimmed. Not paired: Omis
                  nearby as rows, then "Get an Omi" as one quiet row
Apple Watch       status (only when paired; not shown yet, see below)
Listening         language you speak, detect languages, words and names, end after silence,
                  recordings still on the iPhone
  Advanced        speech model, transcribe on this iPhone, transcribe later, transcription log
Voices & people   your voice (record again), people (add, rename, delete, open), asking who
                  spoke, remembering named voices, ignored voices, clean up
Memory            what Omi knows about you (map, counts, facts), import history, delete all
                  memories. Memory visibility lives in the Memories screen's menu.
Assistant         spoken replies, voice (pushed list with previews), proactive tips, daily recap
                  and its time. The one place for tips and the recap.
Apps & integrations   connected / add: calendar, mail, task apps (their settings), Apple Health,
                      Reminders; your installed apps; browse apps (store)
Connect your AI   Claude, ChatGPT or another assistant reads what Omi knows: two lines what
                  it does, then Claude / ChatGPT / Other (MCP) with numbered steps and one
                  action (open Claude, open ChatGPT, create a key and copy its setup)
Phone calls       numbers, new call, call history; a plan upsell when calls are locked
Appearance        System / Light / Dark as three previews, app language (opens iOS settings)
Notifications     iOS permission, what Omi notifies about (links to Assistant for recap and tips)
Privacy & data    keep audio (cloud, this iPhone), location, iOS permissions, which apps see
                  what, export my data, policies
Help              help center, feedback, what's new, replay introduction, developer mode
  Developer       (only when developer mode is on) user ID, webhooks, raw API and MCP keys,
                  experimental switches, logs, docs. Connecting an assistant lives in
                  Connect your AI.
```
Tile values and the avatar's initials are pure logic in `SettingsHub` (OmiService), tested in
`SettingsHubTests`. Apple Watch status waits for the watch store to reach the Settings environment
(the app shell owns it).

## Screens
- Tabs: **Home · Chat · Memories** (word tabs, swipe between the pages). There is no Tasks tab:
  tasks live on Home. The floating Ask Omi bar sits on Home and Memories and switches to Chat.
- Home: "Needs you" (max five cards in this order: the daily tidy-up suggestion, Omi asks,
  finished runs, What matters now, the condensed important tasks, one connection), "Later (n)"
  (tasks put off until tomorrow, the overflow, Omi's running work, tips), "All tasks (n)", then
  conversations by day (recap as the day's first row), goals line. Task cards: kicker (Overdue,
  Due today, Due tomorrow, Someone waits, Suggestion), the task, where it was heard; "Omi takes
  over" or "Done", and "Later"; long press adds Not a task and Open conversation. Tap: the task's
  own screen. Condensing rules: `TaskConsolidation`; the AI tidy-up: `TaskTidyUp`.
- Task (sheet from a Home card, an All tasks row or a task link): text and due date (editable),
  "From" (the conversation and the words), Omi takes over, Done, Later, Not a task, share, delete.
- All tasks (pushed from Home): search + new, buckets; one "…" menu (select, clear completed,
  export, Reminders, day view).
- Memories: search + new, filter chips; one "…" menu (graph, visibility, select).
- Conversation: tabs Summary / Transcript; one "…" menu for every action; star and share in the bar.
- Chat (tab): no bar of its own. The app header's search looks through the thread on this tab
  and the chat's one "…" sits beside it (Talk to Omi or a chat app, Show only: approvals, drafts,
  jobs, files; Clear chat). While the thread is scrolled away from its top, the big "Home Chat
  Memories" words fold into one small row (a large title collapsing) and unfold at its top; Home
  and Memories keep the big words. Under the header only while it applies: the search field with
  filter chips, the offline line, Running now. The thread fades out at its top edge.
  Bubbles as in Messages: yours in a soft Omi blue on the right, Omi's on the card color on the
  left (16 pt, at most 78 % of the width); bubbles of one sender in a row are a group (3 pt
  apart, 12 pt between groups; smaller corners where they join, a quiet tail on the last one),
  Omi's pendant beside the last bubble of an Omi group. A long answer is split into a few
  bubbles where its paragraphs end (never inside a list, table, quote or code; at most four).
  Steps and the app's cards above an answer in Omi's column; the cards compact like bubbles
  (one-line title, at most two pills), cards of one kind in a row stacked ("2 more"), finished
  runs in a row too. Below an answer only on the newest one: source chips and the follow-up
  (only while nothing is typed); an older answer shows "2 sources", which opens its chips; "Stop
  reading" only while that answer is read aloud. Day dividers ("Today", "Yesterday", a weekday,
  a date). No action rows: a long press opens the message's menu (reply, copy, share, read
  aloud, helpful / not helpful, try again on a failed question, hide on this iPhone), a tap
  shows its time. Reply (sent with a one-line quote) is in the long-press menu only: a sideways
  swipe always pages between Home, Chat and Memories. The jump
  arrow shows only once scrolling ends more than 80 pt above the end, above the composer;
  sending, a streaming answer and the keyboard keep the thread at its end while it was there.
  Layout rules (split, groups, extras, stacks, at the end, header fold): `ChatLayout`.
  Composer as in Messages: "+" chip (photo, camera, file, paste), the field with the blue send
  arrow inside (only with text; stop while Omi answers), one mic (tap: dictate, hold: talk and
  send), all 44 pt on one baseline; the field grows to six lines; messages blur under its
  material; dragging the thread down dismisses the keyboard.
  The full-screen chat (from Home) has its own title bar: close, "Talk to…", "…" (clear chat).
