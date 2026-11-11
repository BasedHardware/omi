import 'package:flutter/material.dart';

import 'package:url_launcher/url_launcher.dart';

import 'package:omi/gen/assets.gen.dart';
import 'package:omi/gen/pigeon_communicator.g.dart';
import 'package:omi/ui/ui.dart';
import 'package:omi/utils/error_message.dart';
import 'package:omi/utils/l10n_extensions.dart';

class AppleWatchSetupBottomSheet extends StatefulWidget {
  final String deviceId;
  final VoidCallback? onConnected;

  const AppleWatchSetupBottomSheet({super.key, required this.deviceId, this.onConnected});

  /// Presents [sheet] in the shared sheet shell (docs/ux-contract.md §2).
  static Future<void> show(BuildContext context, {required AppleWatchSetupBottomSheet sheet}) {
    return showOmiSheet<void>(context: context, builder: (_) => sheet);
  }

  @override
  State<AppleWatchSetupBottomSheet> createState() => _AppleWatchSetupBottomSheetState();
}

class _AppleWatchSetupBottomSheetState extends State<AppleWatchSetupBottomSheet> {
  bool _isChecking = false;
  bool? _isAppInstalled;
  bool _isLoading = true;

  @override
  void initState() {
    super.initState();
    _checkAppInstallationStatus();
  }

  Future<void> _checkAppInstallationStatus() async {
    try {
      final hostAPI = WatchRecorderHostAPI();
      final bool isInstalled = await hostAPI.isWatchAppInstalled();

      if (mounted) {
        setState(() {
          _isAppInstalled = isInstalled;
          _isLoading = false;
        });
      }
    } catch (e) {
      if (mounted) {
        setState(() {
          _isAppInstalled = false;
          _isLoading = false;
        });
      }
    }
  }

  @override
  Widget build(BuildContext context) {
    return SingleChildScrollView(
      padding: const EdgeInsets.fromLTRB(OmiSpacing.md, 0, OmiSpacing.md, OmiSpacing.xl),
      child: Column(
        children: [
          ExcludeSemantics(
            child: ClipRRect(
              borderRadius: OmiRadius.lgAll,
              child: Image.asset(Assets.images.appleWatch.path, height: 120, width: 120, fit: BoxFit.cover),
            ),
          ),
          const SizedBox(height: OmiSpacing.xxl),
          if (_isLoading) ...[
            Text(context.l10n.checkingAppleWatch, style: OmiType.title3, textAlign: TextAlign.center),
            const SizedBox(height: OmiSpacing.md),
            const OmiSpinner(),
          ] else ...[
            Text(
              _isAppInstalled == false ? context.l10n.installOmiOnAppleWatch : context.l10n.openOmiOnAppleWatch,
              style: OmiType.title3.copyWith(height: 1.2),
              textAlign: TextAlign.center,
            ),
            const SizedBox(height: OmiSpacing.md),
            Text(
              _isAppInstalled == false
                  ? context.l10n.installOmiOnAppleWatchDescription
                  : context.l10n.openOmiOnAppleWatchDescription,
              style: OmiType.body.copyWith(color: OmiColors.textSecondary),
              textAlign: TextAlign.center,
            ),
          ],
          const SizedBox(height: OmiSpacing.xxl),
          OmiButton(
            label: _getPrimaryButtonText(context),
            expand: true,
            isLoading: _isChecking,
            onPressed: _isLoading ? null : _handlePrimaryAction,
          ),
          const SizedBox(height: OmiSpacing.xs),
          OmiButton.tertiary(label: context.l10n.cancel, expand: true, onPressed: () => Navigator.of(context).pop()),
        ],
      ),
    );
  }

  String _getPrimaryButtonText(BuildContext context) {
    if (_isAppInstalled == false) {
      return context.l10n.openWatchApp;
    } else {
      return context.l10n.iveInstalledAndOpenedTheApp;
    }
  }

  Future<void> _handlePrimaryAction() async {
    if (_isAppInstalled == false) {
      await _launchWatchApp();
    } else {
      await _checkConnection();
    }
  }

  Future<void> _launchWatchApp() async {
    try {
      final url = Uri.parse("itms-watchs://");

      if (await canLaunchUrl(url)) {
        await launchUrl(url);

        if (mounted) {
          Navigator.of(context).pop();
        }
      }
    } catch (e) {
      if (mounted) {
        OmiFeedback.error(context, context.l10n.unableToOpenWatchApp);

        Navigator.of(context).pop();
      }
    }
  }

  Future<void> _checkConnection() async {
    setState(() {
      _isChecking = true;
    });

    try {
      final hostAPI = WatchRecorderHostAPI();
      final bool isReachable = await hostAPI.isWatchReachable();

      if (isReachable) {
        if (mounted) {
          OmiFeedback.confirm(context, context.l10n.appleWatchConnectedSuccessfully);

          // Close the bottom sheet and notify parent
          Navigator.of(context).pop();
        }
        widget.onConnected?.call();
      } else {
        if (mounted) {
          OmiFeedback.info(context, context.l10n.appleWatchNotReachable);
        }
      }
    } catch (e) {
      if (mounted) {
        OmiFeedback.error(context, context.l10n.errorCheckingConnection(readableError(e)));
      }
    } finally {
      if (mounted) setState(() => _isChecking = false);
    }
  }
}
