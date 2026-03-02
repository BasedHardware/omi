# Omi App - Maestro Functional & Performance Tests

Automated UI tests for the Omi mobile app using [Maestro](https://maestro.dev).

## Prerequisites

1. **Maestro CLI**: Install Maestro
   ```bash
   curl -Ls "https://get.maestro.mobile.dev" | bash
   ```

2. **Omi Device**: For full testing, have your Omi device powered on and nearby.

3. **App Build**: Build and install the app on your test device/emulator.

## Running Tests

### Quick Start

Run all functional tests:
```bash
cd app/.maestro
maestro test functional/
```

Run a specific test:
```bash
maestro test functional/01_onboarding_signin.yaml
```

### Test Suites

| Suite | Description | Command |
|-------|-------------|---------|
| All | Complete test suite | `maestro test .` |
| Functional | Core app flows | `maestro test functional/` |
| Performance | Battery/memory/CPU | `maestro test performance/` |

### Test Order (Recommended)

For first-time setup, run tests in order:

1. `01_onboarding_signin.yaml` - Sign in to app
2. `02_device_connection.yaml` - Connect Omi device
3. `03_recording_transcription.yaml` - Test recording
4. `04_conversations_crud.yaml` - Manage conversations
5. `05_memories.yaml` - View memories
6. `06_action_items.yaml` - Check action items
7. `07_apps_plugins.yaml` - Browse/install plugins
8. `08_chat.yaml` - Chat with AI

## Test Coverage

### Functional Tests (`functional/`)

| Test | Coverage |
|------|----------|
| 01_onboarding_signin | Welcome → Sign-in → Name → Permissions → Home |
| 02_device_connection | Bluetooth scanning → Device pairing → Connection |
| 03_recording_transcription | Start → Live transcription → Stop → Save |
| 04_conversations_crud | List → View → Edit → Delete |
| 05_memories | Browse → View details → Interact |
| 06_action_items | List → Mark complete → Delete |
| 07_apps_plugins | Browse → Install → Configure → Uninstall |
| 08_chat | Send message → AI response → History |

### Performance Tests (`performance/`)

| Test | Metrics |
|------|---------|
| 01_extended_session.yaml | Memory stability, CPU spikes, responsiveness over repeated recording cycles |
| 02_continuous_recording.yaml | Battery drain, memory/CPU usage during 30+ min continuous recording |
| 03_memory_leak_detection.yaml | Memory growth over repeated app open/close cycles |
| 04_responsiveness.yaml | UI frame rates, scroll performance, interaction latency |

## Running Extended Tests

For the full 24-hour performance test suite mentioned in issue #3858:

```bash
# Run performance suite with extended timeout
maestro test performance/ --timeout 86400000

# Or run overnight with reporting
maestro test performance/ --format junit --output reports/
```

## Screenshots

All tests capture screenshots at key points. Find them in:
- `~/.maestro/screenshots/` (default)
- Or specify: `maestro test --output ./screenshots/ functional/`

## CI/CD Integration

### GitHub Actions

```yaml
- uses: mobile-dev-inc/action-maestro-cloud@v1
  with:
    api-key: ${{ secrets.MAESTRO_CLOUD_API_KEY }}
    app-file: build/app.apk
    flow: .maestro/functional/
```

### Local CI

```bash
# Build app
flutter build apk --flavor prod

# Run tests
maestro test --format junit --output reports/ .maestro/functional/
```

## Troubleshooting

### Test Fails to Find Element

1. Run `maestro studio` to inspect the app UI
2. Adjust selectors in the YAML file
3. Some selectors use regex patterns to handle locale variations

### Device Not Detected

1. Ensure Bluetooth is enabled
2. Omi device should be in pairing mode
3. Check device battery level

### Slow Tests

1. Increase timeout values in the YAML files
2. Ensure stable network connection
3. Close other apps to free resources

## Contributing

When adding new tests:

1. Follow the naming convention: `##_feature_name.yaml`
2. Add appropriate tags for filtering
3. Include screenshots at key points
4. Test on both Android and iOS
5. Document any preconditions

## Related Issues

- [#3857](https://github.com/BasedHardware/omi/issues/3857) - Functional tests bounty
- [#3858](https://github.com/BasedHardware/omi/issues/3858) - Performance tests bounty
