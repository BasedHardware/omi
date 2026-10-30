import 'dart:async';

import 'package:flutter/material.dart';

import '../art.dart';
import '../theme.dart';
import '../widgets.dart';

/// 05 — Find your Omi. Copy matches `find_device` ("Searching for devices").
///
/// The prototype fakes discovery: after [searchDuration] it reports the
/// device as found. In the app this is the BLE scan.
class FindDeviceScreen extends StatefulWidget {
  const FindDeviceScreen({super.key, required this.onFound, this.searchDuration = const Duration(seconds: 3)});

  final VoidCallback onFound;
  final Duration searchDuration;

  @override
  State<FindDeviceScreen> createState() => _FindDeviceScreenState();
}

class _FindDeviceScreenState extends State<FindDeviceScreen> {
  Timer? _timer;
  bool _showHelp = false;

  @override
  void initState() {
    super.initState();
    _timer = Timer(widget.searchDuration, widget.onFound);
  }

  @override
  void dispose() {
    _timer?.cancel();
    super.dispose();
  }

  @override
  Widget build(BuildContext context) {
    final t = DfThemeScope.of(context);
    return DfPage(
      children: <Widget>[
        const DfProgress(step: 1),
        const DfHeadline('Turn on your Omi'),
        const DfBody('Press its button once and hold it near your phone.'),
        const Center(child: DfPulseRings(size: 260, child: DfPendant(size: 116, showCord: false, glow: true))),
        Row(
          mainAxisAlignment: MainAxisAlignment.center,
          children: <Widget>[
            SizedBox.square(dimension: 16, child: CircularProgressIndicator(strokeWidth: 2, color: t.text)),
            const SizedBox(width: 10),
            Flexible(child: Text('Searching for devices', style: t.label(size: 16))),
          ],
        ),
        if (_showHelp)
          DfCard(
            padding: const EdgeInsets.all(16),
            child: Column(
              crossAxisAlignment: CrossAxisAlignment.start,
              children: <Widget>[
                Text('No Omi Found', style: t.label(weight: FontWeight.w600)),
                const SizedBox(height: 4),
                Text('Turn it on and hold it near your phone.', style: t.body(size: 14)),
              ],
            ),
          ),
        const Spacer(),
        const DfCaption('Omi connects over Bluetooth.'),
        DfButton('How to Pair', onPressed: () => setState(() => _showHelp = true), kind: DfButtonKind.text),
      ],
    );
  }
}

/// 06 — Omi found.
class DeviceFoundScreen extends StatelessWidget {
  const DeviceFoundScreen({super.key, required this.onPair, required this.onScanAgain});

  final VoidCallback onPair;
  final VoidCallback onScanAgain;

  @override
  Widget build(BuildContext context) {
    final t = DfThemeScope.of(context);
    return DfPage(
      children: <Widget>[
        const DfProgress(step: 1),
        const DfEyebrow('1 device found nearby'),
        const DfHeadline('We found your Omi'),
        DfCard(
          padding: const EdgeInsets.symmetric(horizontal: 16, vertical: 14),
          child: Row(
            children: <Widget>[
              const DfPendant(size: 56, showCord: false),
              const SizedBox(width: 14),
              Expanded(
                child: Column(
                  crossAxisAlignment: CrossAxisAlignment.start,
                  children: <Widget>[
                    Text('Omi', style: t.label(size: 17, weight: FontWeight.w600)),
                    const SizedBox(height: 3),
                    Row(
                      children: <Widget>[
                        Icon(Icons.battery_5_bar, size: 16, color: t.textTertiary),
                        const SizedBox(width: 6),
                        Text('Battery 82%', style: t.body(size: 13, color: t.textTertiary)),
                      ],
                    ),
                  ],
                ),
              ),
              Icon(Icons.chevron_right, color: t.textTertiary),
            ],
          ),
        ),
        const Spacer(),
        DfButton('Pair this Omi', onPressed: onPair),
        DfButton('Scan Again', onPressed: onScanAgain, kind: DfButtonKind.text),
      ],
    );
  }
}

/// 07 — Paired.
class PairedScreen extends StatelessWidget {
  const PairedScreen({super.key, required this.onContinue});

  final VoidCallback onContinue;

  @override
  Widget build(BuildContext context) {
    final t = DfThemeScope.of(context);
    return DfPage(
      children: <Widget>[
        const DfProgress(step: 1),
        const Spacer(),
        const Center(child: DfPendant(size: 168, showCord: false, glow: true)),
        DfEyebrow('Pairing successful', color: t.success),
        const DfHeadline('Your Omi is ready to listen.'),
        const DfBody('Wear it on the lanyard or clip it on. When the light is on, Omi is capturing.'),
        const DfCard(
          child: Column(
            children: <Widget>[
              DfListRow(icon: Icons.battery_5_bar, label: 'Battery', value: '82%'),
              DfListRow(icon: Icons.check, label: 'Firmware', value: 'Up to date'),
            ],
          ),
        ),
        const Spacer(),
        DfButton('Continue', onPressed: onContinue),
      ],
    );
  }
}
