import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:omi/backend/schema/bt_device/bt_device.dart';
import 'package:omi/pages/home/firmware_mixin.dart';
import 'package:omi/utils/firmware_update_build_policy.dart';

void main() {
  testWidgets('DAT build exits every Omi DFU entry point before native plugin use', (tester) async {
    final key = GlobalKey<_FirmwareHarnessState>();
    await tester.pumpWidget(MaterialApp(home: _FirmwareHarness(key: key)));
    final state = key.currentState!;
    final device = BtDevice.empty();

    expect(state.managerFactory, isNull);
    await expectLater(state.startDfu(device), completes);
    await expectLater(state.startMCUDfu(device), completes);
    await expectLater(state.startLegacyDfu(device), completes);

    expect(state.isInstalling, isFalse);
  });
}

class _FirmwareHarness extends StatefulWidget {
  const _FirmwareHarness({super.key});

  @override
  State<_FirmwareHarness> createState() => _FirmwareHarnessState();
}

class _FirmwareHarnessState extends State<_FirmwareHarness> with FirmwareMixin<_FirmwareHarness> {
  @override
  FirmwareUpdateBuildPolicy get firmwareUpdatePolicy => const FirmwareUpdateBuildPolicy(rayBanDat: true);

  @override
  Widget build(BuildContext context) => const SizedBox.shrink();
}
