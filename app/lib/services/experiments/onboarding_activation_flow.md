# Onboarding ending: activation flow vs voice introduction

**Status:** pre-registered, not yet started. **Flag:** `onboarding-activation-flow` (PostHog,
mobile, client-evaluated). **Gate:** `onboarding_activation_flow.dart`.

## Hypothesis

New mobile users who end onboarding with the activation flow (Omi at work, a first real
conversation, its summary and to-dos, then the paywall) subscribe within 30 days more often than
users who end with the guided voice introduction.

## Unit, assignment, split

- **Unit:** the PostHog distinct id after sign-in (the Firebase uid). Assignment is PostHog's.
- **Arms:** control = voice introduction, then the flag-gated "Setting up your Omi" page and
  "You're all set". Treatment = activation flow. Every step before (sign-in, consent, name,
  permissions, language, Connect Omi) is the same in both arms.
- **Flag shape:** a boolean flag (on = treatment) or a multivariate experiment flag with
  `control` and `test`. `treatment` and `activation` are also read as treatment; any other value,
  no identity, a timeout or an error is control.
- **Exposure:** the flag is read when the reader reaches Connect Omi, and the arm is fixed for the
  account when they leave it, so a reader who resumes later finishes the same ending.

## Metrics

- **Primary:** subscription started within 30 days of `Onboarding Completed`.
- **Guardrails:** onboarding completion rate from Connect Omi; voice-profile coverage at day 7
  (the activation enrolls only from phone dictation); paywall views during onboarding.
- **Secondary:** opened 3+ conversations within 3 days of first connecting an Omi.

## Decision rule

Ship treatment if the primary metric improves and onboarding completion does not drop by more
than 2 points. Changing the primary metric after enrollment starts needs a new flag key.
