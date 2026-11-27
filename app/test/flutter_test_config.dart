import 'dart:async';

import 'package:flutter/services.dart';
import 'package:flutter_test/flutter_test.dart';

Future<void> testExecutable(FutureOr<void> Function() testMain) async {
  TestWidgetsFlutterBinding.ensureInitialized();
  TestDefaultBinaryMessengerBinding.instance.defaultBinaryMessenger.setMockMethodCallHandler(
    const MethodChannel('com.omi/live_wal_receipt_durability'),
    (call) async {
      if (call.method != 'syncDirectory') {
        throw MissingPluginException('Unsupported live WAL durability method: ${call.method}');
      }
      return null;
    },
  );
  await testMain();
}
