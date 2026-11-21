# flutter_background_service_ios (vendored 5.0.3)

Copy of pub.dev `flutter_background_service_ios` 5.0.3, used through `dependency_overrides` in `app/pubspec.yaml`.

Only change: `registerTaskIdentifier` registers `dev.flutter.background.refresh` once per process.
With UIScene, Flutter sends `application(_:didFinishLaunchingWithOptions:)` to plugins twice on a launch
that carries options (notification tap, link, quick action): once after the storyboard engine registers
plugins and again from `sceneWillConnectFallback`. The second `BGTaskScheduler.register` raised
`NSInternalInconsistencyException` (Crashlytics 6c17570d).

Drop this copy when upstream ships an idempotent registration.
