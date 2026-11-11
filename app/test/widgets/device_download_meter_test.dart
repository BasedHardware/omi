import 'package:flutter/material.dart';
import 'package:flutter_localizations/flutter_localizations.dart';
import 'package:flutter_test/flutter_test.dart';

import 'package:omi/l10n/app_localizations.dart';
import 'package:omi/pages/conversations/widgets/device_download_meter.dart';
import 'package:omi/pages/conversations/widgets/device_storage_card.dart';
import 'package:omi/pages/conversations/widgets/status_action_pill.dart';
import 'package:omi/services/devices/connectors/device_connection.dart';
import 'package:omi/ui/components/omi_spinner.dart';
import 'package:omi/ui/omi_tokens.dart';

const _mb = 1024 * 1024;

Widget _app(Widget child) {
  return MaterialApp(
    theme: ThemeData(fontFamily: 'SFNS', brightness: Brightness.light),
    localizationsDelegates: const [
      AppLocalizations.delegate,
      GlobalMaterialLocalizations.delegate,
      GlobalWidgetsLocalizations.delegate,
      GlobalCupertinoLocalizations.delegate,
    ],
    supportedLocales: AppLocalizations.supportedLocales,
    home: Scaffold(backgroundColor: const Color(0xFFF2F2F7), body: child),
  );
}

void main() {
  setUpAll(() {
    OmiColors.active = OmiPalette.light;
  });

  testWidgets('total card shows a bar plus percent and speed; the row bar has neither', (tester) async {
    await tester.pumpWidget(
      _app(
        RepaintBoundary(
          key: const Key('offline-sync-render'),
          child: Padding(
            padding: const EdgeInsets.all(16),
            child: Column(
              crossAxisAlignment: CrossAxisAlignment.stretch,
              children: [
                Container(
                  padding: const EdgeInsets.symmetric(horizontal: 16, vertical: 15),
                  decoration: BoxDecoration(color: OmiColors.surface1, borderRadius: BorderRadius.circular(16)),
                  child: Column(
                    crossAxisAlignment: CrossAxisAlignment.start,
                    children: [
                      Row(
                        children: [
                          const OmiSpinner(size: OmiSpinnerSize.small),
                          const SizedBox(width: 12),
                          const Expanded(
                            child: Text(
                              'Downloading from your device',
                              style: TextStyle(fontSize: 15, fontWeight: FontWeight.w500, height: 1.25),
                            ),
                          ),
                          statusActionPill('Cancel', Colors.redAccent, () {}),
                        ],
                      ),
                      const SizedBox(height: 10),
                      const DeviceDownloadMeter(fraction: 0.38, speedKBps: 24),
                    ],
                  ),
                ),
                const SizedBox(height: 12),
                DeviceStorageCard(
                  status: RingStatus(usedBytes: 56 * _mb, unreadPackets: 0, freeBytes: 416 * _mb, rtcValid: 1),
                ),
                const SizedBox(height: 12),
                Container(
                  decoration: BoxDecoration(color: OmiColors.surface1, borderRadius: BorderRadius.circular(20)),
                  child: const Column(
                    crossAxisAlignment: CrossAxisAlignment.stretch,
                    children: [
                      _Row(title: 'Today  ·  1:42 PM  ·  1m 15s', subtitle: 'Waiting to sync'),
                      Divider(height: 1, indent: 16, endIndent: 16),
                      _Row(
                        title: 'Today  ·  12:13 PM  ·  1h 28m',
                        subtitle: 'Downloading from your device',
                        fraction: 0.38,
                      ),
                    ],
                  ),
                ),
              ],
            ),
          ),
        ),
      ),
    );
    await tester.pump();
    await tester.pump(const Duration(milliseconds: 50));

    expect(find.text('38% · 24 KB/s'), findsOneWidget);
    expect(find.text('Waiting to sync'), findsOneWidget);
    expect(find.text('Downloading from your device'), findsNWidgets(2));

    final meters = tester.widgetList<DeviceDownloadMeter>(find.byType(DeviceDownloadMeter)).toList();
    expect(meters, hasLength(2));
    expect(meters[0].showReadout, isTrue);
    expect(meters[1].showReadout, isFalse);
    expect(meters[1].fraction, 0.38);

    final cardBar = tester.widget<LinearProgressIndicator>(find.byType(LinearProgressIndicator).at(0));
    expect(cardBar.value, closeTo(0.38, 0.001));
  });

  testWidgets('a waiting row does not invent a percent', (tester) async {
    await tester.pumpWidget(
      _app(const DeviceDownloadMeter(fraction: 0.38, speedKBps: 24, showReadout: false)),
    );
    await tester.pump();
    expect(find.textContaining('%'), findsNothing);
    expect(find.textContaining('KB/s'), findsNothing);
    expect(find.byType(LinearProgressIndicator), findsOneWidget);
  });
}

class _Row extends StatelessWidget {
  const _Row({required this.title, required this.subtitle, this.fraction});

  final String title;
  final String subtitle;
  final double? fraction;

  @override
  Widget build(BuildContext context) {
    return Padding(
      padding: const EdgeInsets.symmetric(horizontal: 16, vertical: 14),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          Text(title, style: const TextStyle(fontSize: 15, fontWeight: FontWeight.w500)),
          const SizedBox(height: 3),
          Text(subtitle, style: TextStyle(color: Colors.grey.shade500, fontSize: 12)),
          if (fraction != null) ...[
            const SizedBox(height: 8),
            DeviceDownloadMeter(fraction: fraction!, showReadout: false, barHeight: 4),
          ],
        ],
      ),
    );
  }
}
