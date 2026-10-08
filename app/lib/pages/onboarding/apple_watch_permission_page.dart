import 'package:flutter/material.dart';

import 'package:omi/mobile/native_ui/ios_native_surface.dart';
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

  /// A native row's request is running; like the classic button's spinner, it blocks a second tap.
  bool _working = false;

  Future<void> _once(Future<void> Function() request) async {
    if (_working) return;
    setState(() => _working = true);
    try {
      await request();
    } finally {
      if (mounted) setState(() => _working = false);
    }
  }

  @override
  Widget build(BuildContext context) {
    final l10n = context.l10n;
    return IosNativeSurface(
      title: l10n.appleWatchSetup,
      fallback: _classic(context),
      toolbar: [
        NativeRow('watch_permission_back', l10n.back,
            symbol: 'chevron.left', action: (_) => Navigator.of(context).maybePop()),
      ],
      sections: [
        NativeSection('watch_permission', [
          NativeRow(
            'watch_permission_status',
            _permissionRequested ? l10n.permissionRequestedExclaim : l10n.microphonePermission,
            subtitle: _permissionRequested ? l10n.permissionGrantedNow : l10n.needMicrophonePermission,
            kind: 'label',
            symbol: 'mic',
          ),
        ]),
        NativeSection('watch_permission_actions', [
          if (!_permissionRequested)
            NativeRow('watch_permission_grant', l10n.grantPermissionButton,
                enabled: !_working, action: (_) => _once(_requestPermission))
          else ...[
            NativeRow('watch_permission_continue', l10n.continueButton,
                enabled: !_working, action: (_) => _once(_continueAndStartRecording)),
            NativeRow('watch_permission_help', l10n.needHelp,
                symbol: 'questionmark.circle', action: (_) => _showHelpDialog()),
          ],
        ]),
      ],
    );
  }

  Widget _classic(BuildContext context) {
    return Scaffold(
      backgroundColor: OmiColors.surface0,
      appBar: AppBar(
        leading: const OmiBackButton(),
        title: Text(context.l10n.appleWatchSetup),
      ),
      body: SafeArea(
        child: SingleChildScrollView(
          padding: const EdgeInsets.all(OmiSpacing.xxl),
          child: Column(
            children: [
              const SizedBox(height: OmiSpacing.xxl),
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
                child: Text(
                  _permissionRequested ? context.l10n.permissionRequestedExclaim : context.l10n.microphonePermission,
                  style: OmiType.title1.copyWith(height: 1.2),
                  textAlign: TextAlign.center,
                ),
              ),
              const SizedBox(height: OmiSpacing.xl),
              Text(
                _permissionRequested ? context.l10n.permissionGrantedNow : context.l10n.needMicrophonePermission,
                style: OmiType.body.copyWith(color: OmiColors.textSecondary, height: 1.6),
                textAlign: TextAlign.center,
              ),
              const SizedBox(height: 48),
              if (!_permissionRequested)
                OmiButton(
                  label: context.l10n.grantPermissionButton,
                  expand: true,
                  onPressed: _requestPermission,
                )
              else ...[
                OmiButton(label: context.l10n.continueButton, expand: true, onPressed: _continueAndStartRecording),
                const SizedBox(height: OmiSpacing.md),
                OmiButton.tertiary(label: context.l10n.needHelp, onPressed: _showHelpDialog),
              ],
            ],
          ),
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
