import 'package:flutter/material.dart';

import 'src/launcher.dart';

/// Design prototype of the device-first onboarding flow and soft paywall.
/// See README.md for how to run it.
void main() => runApp(const DeviceFirstPrototypeApp());

class DeviceFirstPrototypeApp extends StatelessWidget {
  const DeviceFirstPrototypeApp({super.key});

  @override
  Widget build(BuildContext context) {
    return MaterialApp(
      title: 'Omi device-first prototype',
      debugShowCheckedModeBanner: false,
      theme: ThemeData(brightness: Brightness.dark, useMaterial3: true),
      home: const PrototypeLauncher(),
    );
  }
}
