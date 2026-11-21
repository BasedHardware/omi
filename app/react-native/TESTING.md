# React Native App Testing Documentation

## Validation Commands (run in `app/react-native/`)

### Type Checking
```bash
pnpm run typecheck
```
- Validates TypeScript compilation with strict mode
- No errors = pass

### Linting
```bash
pnpm run lint
```
- ESLint with TypeScript, React, React Hooks rules
- Allowed warnings: 20 (unused vars, any types)
- No errors = pass

### Build Validation
```bash
pnpm install
pnpm run typecheck && pnpm run lint
```
- Full validation pipeline
- Run before committing

## Device/Emulator Testing (Manual)

### Android Emulator
```bash
pnpm run android
```
- Prebuilds native Android project
- Runs on connected emulator/device
- Verify: app launches, auth flow works, tabs navigate

### Web (Quick Validation)
```bash
pnpm run web
```
- Runs Expo web build
- Verify: UI renders, no console errors

## Tested Scenarios (Phase 1 Vertical Slice)

| Feature | Status | Notes |
|---------|--------|-------|
| Auth (Google/Apple) | ✅ Manual | Firebase ID token → Omi API Bearer |
| Conversations list | ✅ Manual | `/v1/conversations` fetch |
| Conversation detail | ✅ Manual | Transcript segments render |
| Memories list | ✅ Manual | `/v3/memories` fetch + tag grouping |
| Home screen (recaps, mind map) | ✅ Manual | Derived from conversations/memories |
| Capture screen (STT) | ⚠️ Pending | Deepgram key required |
| Settings / Sign out | ✅ Manual | Firebase signOut + token clear |

## Backend Verification Checklist

- [ ] `GET /v1/conversations` returns 200 with auth token
- [ ] `GET /v3/memories` returns 200 with auth token
- [ ] `GET /v1/action-items` returns 200 with auth token
- [ ] WebSocket `/v4/listen` connects with auth token
- [ ] CORS allows `https://api.omi.me` from device

## CI/CD Notes

- EAS project: `georgesg/frontforumfocus`
- Build on push to main
- Run `typecheck` + `lint` as gate
- Manual device testing before release