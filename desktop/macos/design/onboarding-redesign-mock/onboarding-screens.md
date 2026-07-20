# Omi desktop onboarding — screens & what they do

The official flow is **18 steps** (`OnboardingFlow.steps`), rendered through `OnboardingStepScaffold`
(top progress + eyebrow + title + body + footer). Grouped into 5 sections for the grouped-bar mock.

Two things run **in the background** the whole time, not tied to one screen:
- **Profile enrichment** — once the file scan starts, Omi runs a file scan + **Gmail** + **Calendar** + **web research about you** in parallel, plus **Apple Notes** and any **memory-log import** (ChatGPT/Claude export). Status line: *"Reading Gmail, calendar, and Apple Notes…"*. This is what makes "Your 2nd brain is live" real by the time you reach it.
- **Permission probing** — each permission page silently re-checks its own grant state so the button flips to *Granted* the moment you toggle it in System Settings.

---

## Section 1 — About you  (steps 1–4, unskippable)

| # | Screen | Design | What it does |
|---|--------|--------|--------------|
| 1 | **Name** | Eyebrow "Name", title *"What should Omi call you?"*, single text field | Captures the display name Omi uses to address you. Personalization seed. |
| 2 | **Language** | Title *"Pick every language you speak."*, multi-select chips (first = primary) + "Other…" | Sets speech-to-text / assistant languages. First pick is the primary language for prompts and summaries. |
| 3 | **How did you hear** | Eyebrow "Quick question", title *"How did you hear about Omi?"*, source chips (YouTube, Twitter, Friend, Podcast, Product Hunt…) | Attribution/marketing analytics. No personalization value — just where you came from. |
| 4 | **Trust** | Eyebrow "Before we continue", title *"I'm going to ask for a few permissions."*, three preview rows (Screen + files, Microphone, Accessibility + automation) + open-source note | Sets expectations before the real permission prompts. Explains *why* the coming permissions are needed and that Omi is open source / private. No permission requested yet. |

## Section 2 — Permissions  (steps 5–10)

| # | Screen | Design | What it does |
|---|--------|--------|--------------|
| 5 | **Screen Recording** | Eyebrow "Permission", title *"Let Omi read your screen."*, permission card + "Open System Settings" | Requests Screen Recording. **Only permission that needs an app relaunch to apply** (macOS evaluates it per window-server connection at launch). Page polls until granted. |
| 6 | **Full Disk Access** | Eyebrow "Access", title *"Let Omi scan your work."* | Requests Full Disk Access (no prompt API — deep-links to the Settings pane, then probes via `tccd` per file op). Lets Omi index projects/files. |
| 7 | **File Scan** | Eyebrow "Discovery", title *"Start building your profile."*, scanning card | **Kicks off the background profile build** — scans recent files/projects and (in parallel) starts Gmail + Calendar + web research. This is the "labor illusion" moment where enrichment begins. |
| 8 | **Microphone** | Eyebrow "Permission", title *"Let Omi use your mic."* | Native mic prompt (`AVCaptureDevice`). Enables meeting/voice-note transcription. |
| 9 | **Accessibility** | Eyebrow "Permission", title *"Let Omi see the active app."* | Accessibility permission (Settings toggle, probed via `AXIsProcessTrusted`). Lets Omi know which app is active so context follows you. |
| 10 | **Automation** | Eyebrow "Permission", title *"Let Omi act when asked."* | Automation/AppleScript permission. Lets Omi take actions in your apps when you ask. |

## Section 3 — Shortcuts  (steps 11–14)

| # | Screen | Design | What it does |
|---|--------|--------|--------------|
| 11 | **Floating Bar shortcut** | Eyebrow "Shortcut", *"Set your Ask shortcut."*, key caps (⌘O), "does it light up?" test | Registers the global shortcut that opens the Floating Bar (Ask Omi). Live-detects the keypress to confirm it works. |
| 12 | **Floating Bar demo** | Eyebrow "Try it", *"Ask Omi anything."*, mock bar ("Which computer should I buy?") | Hands-on demo: press the shortcut, type a question, see Omi answer using your screen context. Teaches the core interaction. |
| 13 | **Voice shortcut** | Eyebrow "Shortcut", *"Set your voice shortcut."*, key cap (⌥ hold), press-and-hold test | Registers the push-to-talk shortcut. Live-detects the hold. |
| 14 | **Voice demo** | Eyebrow "Try it", *"Hold and ask."*, "Try asking: What's on my screen?" | Hands-on: hold the shortcut, speak, release — Omi listens and answers out loud. |

## Section 4 — Sources  (steps 15–16)

| # | Screen | Design | What it does |
|---|--------|--------|--------------|
| 15 | **Data sources** | Title *"Your 2nd brain is live."*, connected-source rows (Calendar, Email) | Shows the enrichment payoff — the sources Omi has connected/read (Calendar, Email, Notes). Confirms your second brain is populated. |
| 16 | **Exports** | Title *"Put your memories where you work."*, destination chips (Claude, ChatGPT, Cursor, Notion) | Lets you pipe your memories/prompt pack into other tools over MCP. Copies a prompt + memory pack and opens the destination. |

## Section 5 — Goals  (steps 17–18)

| # | Screen | Design | What it does |
|---|--------|--------|--------------|
| 17 | **Goal** | Eyebrow "Goal", title *"Pick one goal."*, single-select goal chips | Captures one focus so Omi can tailor what it surfaces (the personalization signal the flow was otherwise missing). |
| 18 | **Tasks** | Title *"Here's where you'll start."*, task/loose-end rows pulled from your data | Shows real first actions Omi found (e.g. an unanswered email, a dropped follow-up) — the "handed me back something I dropped" wow moment. Ends the flow ("Take me to Omi"). |

---

### Notes
- **Unskippable:** steps 1–4 (Name, Language, How-you-heard, Trust). Everything else has a Skip.
- **The mocks** (`onboarding-official-grouped.html`, `onboarding-grouped.html`) keep this flow but collapse the 18 top dots into these 5 sections, each filling as you move through its steps.
- **Less certain / flagged:** exact moment Gmail/Calendar auth happens (assumed to piggy-back on the file-scan start at step 7) and whether every source needs prior sign-in — verify against `OnboardingPagedIntroCoordinator.startFileScanIfNeeded` before quoting timings externally.
