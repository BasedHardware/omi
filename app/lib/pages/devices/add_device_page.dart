import 'dart:async';

import 'package:flutter/material.dart';

import 'package:provider/provider.dart';

import 'package:omi/pages/capture/connect.dart';
import 'package:omi/pages/devices/device_picker.dart';
import 'package:omi/pages/home/widgets/battery_info_widget.dart';
import 'package:omi/providers/capture_provider.dart';
import 'package:omi/providers/home_provider.dart';
import 'package:omi/ui/ui.dart';
import 'package:omi/utils/enums.dart';
import 'package:omi/utils/l10n_extensions.dart';
import 'package:omi/utils/other/temp.dart';

/// "What will you wear?" (Rev 3 PickDevice) from the Devices tab: every kind of device Omi records
/// from, one tap from its setup ([DevicePickerGroups]); this phone starts recording on Today.
class AddDevicePage extends StatelessWidget {
  const AddDevicePage({super.key});

  void _connect(BuildContext context) {
    OmiHaptics.selection();
    routeToPage(context, const ConnectDevicePage());
  }

  /// Back to Today and start recording with this phone, as the record button would.
  void _useThisPhone(BuildContext context) {
    OmiHaptics.selection();
    final capture = context.read<CaptureProvider>();
    final alreadyRecording = capture.recordingState == RecordingState.record || capture.isPhoneMicPaused;
    final navigator = Navigator.of(context);
    context.read<HomeProvider>().setIndex(0);
    navigator.popUntil((route) => route.isFirst);
    if (!alreadyRecording) unawaited(PhoneCapture.start(navigator.context));
  }

  @override
  Widget build(BuildContext context) {
    final l10n = context.l10n;
    return Scaffold(
      backgroundColor: OmiColors.surface0,
      appBar: const OmiAppBar(leading: OmiBackButton()),
      body: ListView(
        padding: EdgeInsets.fromLTRB(
          OmiSize.screenMargin,
          0,
          OmiSize.screenMargin,
          MediaQuery.paddingOf(context).bottom + OmiSpacing.xl,
        ),
        children: [
          Padding(
            padding: const EdgeInsets.symmetric(horizontal: OmiSpacing.xxs),
            child: Column(
              crossAxisAlignment: CrossAxisAlignment.start,
              children: [
                Semantics(header: true, child: Text(l10n.whatWillYouWear, style: OmiType.largeTitle)),
                const SizedBox(height: 2),
                Text(l10n.pickDeviceSubtitle, style: OmiType.subhead.copyWith(color: OmiColors.textSecondary)),
              ],
            ),
          ),
          const SizedBox(height: 22),
          DevicePickerGroups(onConnect: () => _connect(context), onUsePhone: () => _useThisPhone(context)),
        ],
      ),
    );
  }
}
