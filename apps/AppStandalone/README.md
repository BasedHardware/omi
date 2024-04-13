# Friend

A new Flutter project.

## Getting Started

FlutterFlow projects are built to run on the Flutter _stable_ release.
## Integration Tests

To test on a real iOS / Android device, first connect the device and run the following command from the root of the project:

```bash
flutter test integration_test/test.dart
```

To test on a web browser, first launch `chromedriver` as follows:
```bash
chromedriver --port=4444
```

You may need to run this if you get the following error

Error
```
lib/env/env.dart:2:6: Error: Error when reading 'lib/env/env.g.dart': No such file or directory
part 'env.g.dart';
```
Command
```
flutter pub run build_runner build
```

Then from the root of the project, run the following command:
```bash
flutter drive \
  --driver=test_driver/integration_test.dart \
  --target=integration_test/test.dart \
  -d chrome
```

Find more information about running Flutter integration tests [here](https://docs.flutter.dev/cookbook/testing/integration/introduction#5-run-the-integration-test).

Refer to this guide for instructions on running the tests on [Firebase Test Lab](https://github.com/flutter/flutter/tree/main/packages/integration_test#firebase-test-lab).
