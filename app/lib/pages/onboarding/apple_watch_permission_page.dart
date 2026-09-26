import 'package:flutter/material.dart';

import 'package:omi/services/devices/connectors/apple_watch_connection.dart';
import 'package:omi/ui/ui.dart';
import 'package:omi/utils/error_message.dart';
import 'package:omi/utils/l10n_extensions.dart';

class AppleWatchPermissionPage extends StatefulWidget {
  final AppleWatchDeviceConnection connection;
  final VoidCallback? onPermissionGranted;

  const AppleWatchPermissionPage({super.key, required this.connection, this.onPermissionGranted});

  @override
  State<AppleWatchPermissionPage> createState() => _AppleWatchPermissionPageState();
}

class _AppleWatchPermissionPageState extends State<AppleWatchPermissionPage> {
  bool _permissionRequested = false;

  @override
  Widget build(BuildContext context) {
    return Scaffold(
      backgroundColor: OmiColors.surface0,
      appBar: OmiAppBar(
        leading: const OmiBackButton(),
        title: Text(context.l10n.appleWatchSetup),
      ),
      // The step layout: what the permission is for scrolls; the buttons sit pinned where
      // Continue does on every first-run step (16pt sides, 8pt above the bottom safe area).
      body: SafeArea(
        child: Column(
          crossAxisAlignment: CrossAxisAlignment.stretch,
          children: [
            Expanded(
              child: SingleChildScrollView(
                padding: const EdgeInsets.fromLTRB(OmiSpacing.lg, OmiSpacing.xl, OmiSpacing.lg, OmiSpacing.md),
                child: Column(
                  children: [
                    // Apple Watch image
                    ExcludeSemantics(
                      child: ClipRRect(
                        borderRadius: OmiRadius.xlAll,
                        child: Image.asset('assets/images/apple_watch.png', width: 160, height: 160, fit: BoxFit.cover),
                      ),
                    ),
                    const SizedBox(height: 48),
                    Semantics(
                      header: true,
                      child: OmiBalancedText(
                        _permissionRequested
                            ? context.l10n.permissionRequestedExclaim
                            : context.l10n.microphonePermission,
                        style: OmiType.title1.copyWith(height: 1.2),
                        textAlign: TextAlign.center,
                      ),
                    ),
                    const SizedBox(height: OmiSpacing.xl),
                    OmiBalancedText(
                      _permissionRequested ? context.l10n.permissionGrantedNow : context.l10n.needMicrophonePermission,
                      style: OmiType.body.copyWith(color: OmiColors.textSecondary, height: 1.6),
                      textAlign: TextAlign.center,
                    ),
                  ],
                ),
              ),
            ),
            Padding(
              padding: const EdgeInsets.fromLTRB(OmiSpacing.md, 0, OmiSpacing.md, OmiSpacing.xs),
              child: Column(
                mainAxisSize: MainAxisSize.min,
                crossAxisAlignment: CrossAxisAlignment.stretch,
                children: [
                  if (!_permissionRequested)
                    OmiButton(
                      label: context.l10n.grantPermissionButton,
                      expand: true,
                      onPressed: _requestPermission,
                    )
                  else ...[
                    OmiButton(label: context.l10n.continueButton, expand: true, onPressed: _continueAndStartRecording),
                    OmiButton.tertiary(label: context.l10n.needHelp, onPressed: _showHelpDialog),
                  ],
                ],
              ),
            ),
          ],
        ),
      ),
    );
  }

  /// The button shows its own spinner while this runs.
  Future<void> _requestPermission() async {
    try {
      await widget.connection.requestPermissionAndStartRecording();
      if (mounted) setState(() => _permissionRequested = true);
    } catch (e) {
      if (mounted) OmiFeedback.error(context, context.l10n.errorRequestingPermission(readableError(e)));
    }
  }

  Future<void> _continueAndStartRecording() async {
    try {
      final bool recordingStarted = await widget.connection.checkPermissionAndStartRecording();

      if (recordingStarted) {
        if (mounted) OmiFeedback.confirm(context, context.l10n.recordingStartedSuccessfully);

        widget.onPermissionGranted?.call();
        if (mounted) {
          Navigator.of(context).pop();
        }
      } else {
        if (mounted) OmiFeedback.info(context, context.l10n.permissionNotGrantedYet);
      }
    } catch (e) {
      if (mounted) OmiFeedback.error(context, context.l10n.errorStartingRecording(readableError(e)));
    }
  }

  void _showHelpDialog() {
    showOmiAlert(
      context,
      title: context.l10n.needHelp,
      message: context.l10n.troubleshootingSteps,
      okLabel: context.l10n.gotIt,
    );
  }
}
