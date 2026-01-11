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

### Option 2: Build watchOS alongside iOS app

If you need both iOS and watchOS to build together:

1. Open `Runner.xcodeproj/project.pbxproj` in a text editor
2. Find the line with `/* watchOS dependency disabled by default - uncomment to enable: 42A7BA3D2E788BD400138969 */`
3. Uncomment it to restore: `42A7BA3D2E788BD400138969 /* PBXTargetDependency */,`
4. Find the line with `/* watchOS embed disabled by default - uncomment to enable: 42A7BA3E2E788BD400138969 */`
5. Uncomment it to restore: `42A7BA3E2E788BD400138969 /* omiWatchApp.app in Embed Watch Content */,`

**Important**: Don't commit these changes. Revert them after watchOS development to keep the default behavior for other developers.

## Why is this disabled by default?

The watchOS target can cause build errors in the iOS simulator, especially when:
- watchOS SDKs are missing or outdated
- Simulator versions don't match
- Not all developers need watchOS functionality

This setup ensures smooth iOS development while keeping watchOS easily accessible for those who need it.
