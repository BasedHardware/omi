# settings

Destination `/settings`: Account, Privacy, Developer (`model.ts` is the nav source of truth).

- `model.ts` — section ids, webhook UI↔API names, quick-nav
- `api.ts` — language, billing, keys, webhooks, export, vocabulary
- `ui/SettingsPage.tsx` — shell (`?section=` + loaders)
- `ui/AccountSection.tsx`, `PrivacySection.tsx`, `DeveloperSection.tsx`, `ProfileSection.tsx` — section trees

Public entry: `index.ts`.
