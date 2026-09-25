import 'package:flutter/material.dart';

import 'package:omi/pages/settings/device_settings.dart';

/// The device page as reached from the home header's battery pill.
///
/// An alias: [DeviceSettings] (`pages/settings/device_settings.dart`) is the canonical device
/// page, and every entry point shows the same one. New code should push [DeviceSettings]
/// directly; this name stays so existing callers keep compiling.
class ConnectedDevice extends StatelessWidget {
  const ConnectedDevice({super.key});

  @override
  Widget build(BuildContext context) => const DeviceSettings();
}
