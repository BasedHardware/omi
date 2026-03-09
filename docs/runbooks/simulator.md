### Running the iOS Simulator

```bash
xcrun simctl list devices | grep Booted  # get device ID
cd app && flutter run -d <device-id> --flavor dev   # dev backend (api.omiapi.com)
cd app && flutter run -d <device-id> --flavor prod   # prod backend (api.omi.me)
```

See `/local-dev mobile` skill for full setup details, env file configuration, and troubleshooting.

### Simulator Hot Restart

When the iOS Simulator is running, trigger a hot restart after finishing edits — do not wait for the user to do it manually:

```bash
kill -SIGUSR2 $(pgrep -f "flutter run" | head -1)
```

Use `SIGUSR1` for hot reload (widget/UI-only changes) or `SIGUSR2` for hot restart (logic, state, provider changes). When in doubt, use `SIGUSR2`.
