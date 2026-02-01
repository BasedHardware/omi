# Flutter Build

Build Flutter app for different platforms.

## Purpose

Build the Flutter app for iOS, Android, macOS, or Windows with proper configuration.

## Build Commands

### iOS

```bash
cd app
flutter build ios --flavor dev
flutter build ios --flavor prod --release
```

### Android

```bash
cd app
flutter build apk --flavor dev
flutter build apk --flavor prod --release

# App bundle for Play Store
flutter build appbundle --flavor prod --release
```

### macOS

```bash
cd app
flutter build macos --flavor dev
flutter build macos --flavor prod --release
```

### Windows

```bash
cd app
flutter build windows --flavor dev
flutter build windows --flavor prod --release
```

## Build Configuration

### Flavors

- **dev**: Development backend
- **prod**: Production backend

### Environment Files

- `.dev.env` - Development environment
- Production configured via Firebase

## Pre-Build Checklist

1. **Run tests**
   ```bash
   cd app
   ./test.sh
   ```

2. **Format code**
   ```bash
   dart format --line-length 120 app/
   ```

3. **Check dependencies**
   ```bash
   flutter pub get
   ```

4. **Verify Firebase config**
   - Check Firebase options files
   - Verify bundle IDs
   - Check signing configuration

## Platform-Specific Requirements

### iOS

- Xcode installed
- CocoaPods dependencies installed
- Signing configured
- Bundle ID set

### Android

- Android SDK installed
- NDK installed (for Opus)
- Signing key configured
- Package name set

### macOS

- Xcode installed
- CocoaPods dependencies installed
- Signing configured

### Windows

- Visual Studio with C++ tools
- CMake installed

## Related Documentation

- Flutter Setup: `.cursor/commands/flutter-setup.md`
- App Setup: `docs/doc/developer/AppSetup.mdx`

## Related Cursor Resources

### Rules
- `.cursor/rules/flutter-architecture.mdc` - App structure
- `.cursor/rules/flutter-platform-specific.mdc` - Platform-specific build requirements
- `.cursor/rules/formatting.mdc` - Code formatting before build

### Skills
- `.cursor/skills/omi-flutter-patterns/` - Flutter patterns including builds

### Subagents
- `.cursor/agents/flutter-developer/` - Can help with builds

### Commands
- `/flutter-setup` - Setup Flutter environment
- `/flutter-test` - Test before building
- `/format` - Format code before building
