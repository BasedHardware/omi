// Isolated debug target for native contrast evidence; no auth, sync, or recording I/O.
// From app/: flutter run --debug --flavor dev -t integration_test/offline_sync_contrast_capture.dart.
// Uses the separate dev app identity. Remove only that test app after capturing evidence.
import 'package:flutter/material.dart';
import 'package:marionette_flutter/marionette_flutter.dart';
import 'package:omi/l10n/app_localizations.dart';
import 'package:omi/pages/conversations/widgets/empty_conversations.dart';
import 'package:omi/pages/conversations/widgets/offline_sync_storage_sheet.dart';
import 'package:omi/services/wals/storage_clear.dart';
import 'package:omi/ui/ui.dart';
import 'package:omi/utils/l10n_extensions.dart';

// Synthetic sample: 2 h uploaded, 3 h waiting (2 h on the phone, 1 h on the pendant).
const _sampleAmounts = StorageAmounts(
  uploadedSeconds: 2 * 3600,
  uploadedCount: 2,
  phonePendingSeconds: 2 * 3600,
  devicePendingSeconds: 3600,
  pendingCount: 3,
  allCount: 5,
  allSeconds: 5 * 3600,
);

void main() {
  MarionetteBinding.ensureInitialized();
  runApp(const _ContrastCapture());
}

class _ContrastCapture extends StatefulWidget {
  const _ContrastCapture();
  @override
  State<_ContrastCapture> createState() => _ContrastCaptureState();
}

class _ContrastCaptureState extends State<_ContrastCapture> {
  Brightness _brightness = Brightness.light;
  bool _hasRecordings = false;
  @override
  Widget build(BuildContext context) {
    OmiColors.active = OmiColors.forBrightness(_brightness);
    return MaterialApp(
      debugShowCheckedModeBanner: false,
      theme: buildOmiTheme(brightness: _brightness),
      localizationsDelegates: AppLocalizations.localizationsDelegates,
      supportedLocales: AppLocalizations.supportedLocales,
      home: Builder(
          builder: (context) => Scaffold(
                appBar: AppBar(title: Text(context.l10n.offlineSync)),
                body: Column(children: [
                  const Expanded(child: Center(child: NoConversationsHero())),
                  OmiButton(
                    label: context.l10n.manageStorage,
                    onPressed: () => showOmiSheet<void>(
                      context: context,
                      title: context.l10n.manageStorage,
                      padding: const EdgeInsets.fromLTRB(OmiSpacing.xl, OmiSpacing.xs, OmiSpacing.xl, OmiSpacing.xl),
                      builder: (_) => OfflineSyncStorageSheet(
                        amounts: _hasRecordings ? _sampleAmounts : StorageAmounts.of(const []),
                        onFreeUpSpace: () {},
                        onDeletePending: () {},
                        onDeleteAll: () {},
                      ),
                    ),
                  ),
                  TextButton(
                    onPressed: () => setState(
                        () => _brightness = _brightness == Brightness.light ? Brightness.dark : Brightness.light),
                    child: const Text('Toggle appearance'),
                  ),
                  TextButton(
                    onPressed: () => setState(() => _hasRecordings = !_hasRecordings),
                    child: const Text('Toggle sample counts'),
                  ),
                  const SizedBox(height: 24),
                ]),
              )),
    );
  }
}
