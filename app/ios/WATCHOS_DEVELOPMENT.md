# watchOS Development Guide

By default, the watchOS app (`omiWatchApp`) is **disabled** to prevent build errors in the iOS simulator during regular development.

## Running the iOS app (default)

Use the `dev` or `prod` schemes as normal:
```bash
flutter run --flavor dev
# or
flutter run --flavor prod
```

The watchOS app will not be built automatically.

## Enabling watchOS Development

To work on the watchOS app:

### Option 1: Use the dedicated watchOS scheme (Recommended)

In Xcode:
1. Open `Runner.xcworkspace`
2. Select the **omiWatchApp** scheme from the scheme selector
3. Choose a watchOS simulator or device as the run destination
4. Build and run

### Option 2: Modify the dev/prod schemes temporarily

If you need both iOS and watchOS to build together:

1. Open `Runner.xcodeproj/xcshareddata/xcschemes/dev.xcscheme` (or `prod.xcscheme`)
2. Change `buildImplicitDependencies = "NO"` to `buildImplicitDependencies = "YES"` in the `<BuildAction>` tag
3. Build your iOS app - the watchOS app will now build alongside it

**Important**: Don't commit this change. Revert it after watchOS development to keep the default behavior for other developers.

## Why is this disabled by default?

The watchOS target can cause build errors in the iOS simulator, especially when:
- watchOS SDKs are missing or outdated
- Simulator versions don't match
- Not all developers need watchOS functionality

This setup ensures smooth iOS development while keeping watchOS easily accessible for those who need it.
