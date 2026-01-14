import 'package:flutter/material.dart';

import 'package:omi/services/devices/apple_watch_connection.dart';
import 'package:omi/utils/alerts/app_snackbar.dart';
import 'package:omi/utils/l10n_extensions.dart';
import 'package:omi/utils/responsive/responsive_helper.dart';

class AppleWatchPermissionPage extends StatefulWidget {
  final AppleWatchDeviceConnection connection;
  final VoidCallback? onPermissionGranted;

  const AppleWatchPermissionPage({
    super.key,
    required this.connection,
    this.onPermissionGranted,
  });

  @override
  State<AppleWatchPermissionPage> createState() => _AppleWatchPermissionPageState();
}

class _AppleWatchPermissionPageState extends State<AppleWatchPermissionPage> {
  bool _isRequestingPermission = false;
  bool _permissionRequested = false;

  @override
  Widget build(BuildContext context) {
    final responsive = ResponsiveHelper(context);

    return Scaffold(
      backgroundColor: ResponsiveHelper.backgroundPrimary,
      appBar: AppBar(
        backgroundColor: ResponsiveHelper.backgroundPrimary,
        elevation: 0,
        leading: IconButton(
          icon: const Icon(Icons.arrow_back, color: ResponsiveHelper.textPrimary),
          onPressed: () => Navigator.of(context).pop(),
        ),
        title: Text(
          context.l10n.appleWatchSetup,
          style: const TextStyle(color: ResponsiveHelper.textPrimary),
        ),
      ),
      body: SafeArea(
        child: Padding(
          padding: const EdgeInsets.all(32.0),
          child: Column(
            children: [
              const Spacer(),

              // Apple Watch image
              AnimatedContainer(
                duration: const Duration(milliseconds: 300),
                height: 160,
                width: 160,
                decoration: BoxDecoration(
                  borderRadius: BorderRadius.circular(24),
                  boxShadow: responsive.mediumShadow,
                ),
                child: ClipRRect(
                  borderRadius: BorderRadius.circular(24),
                  child: Image.asset(
                    'assets/images/apple_watch.png',
                    fit: BoxFit.cover,
                  ),
                ),
              ),
              const SizedBox(height: 48),

              // Title
              Text(
                _permissionRequested ? context.l10n.permissionRequestedExclaim : context.l10n.microphonePermission,
                style: responsive.titleLarge.copyWith(
                  fontSize: 28,
                  height: 1.2,
                ),
                textAlign: TextAlign.center,
              ),
              const SizedBox(height: 24),

              // Instructions
              Text(
                _permissionRequested ? context.l10n.permissionGrantedNow : context.l10n.needMicrophonePermission,
                style: responsive.bodyLarge.copyWith(
                  height: 1.6,
                ),
                textAlign: TextAlign.center,
              ),
              const SizedBox(height: 48),

              // Action buttons
              if (!_permissionRequested) ...[
                // Grant Permission Button
                SizedBox(
                  width: double.infinity,
                  height: 56,
                  child: ElevatedButton(
                    onPressed: _isRequestingPermission ? null : _requestPermission,
                    style: ElevatedButton.styleFrom(
                      backgroundColor: ResponsiveHelper.purplePrimary,
                      foregroundColor: Colors.white,
                      shape: RoundedRectangleBorder(
                        borderRadius: BorderRadius.circular(16),
                      ),
                      elevation: 0,
                    ),
                    child: _isRequestingPermission
                        ? const SizedBox(
                            height: 24,
                            width: 24,
                            child: CircularProgressIndicator(
                              strokeWidth: 2,
                              valueColor: AlwaysStoppedAnimation<Color>(Colors.white),
                            ),
                          )
                        : Text(
                            context.l10n.grantPermissionButton,
                            style: const TextStyle(
                              fontSize: 18,
                              fontWeight: FontWeight.w600,
                            ),
                          ),
                  ),
                ),
              ] else ...[
                // Continue Button (after permission was requested)
                SizedBox(
                  width: double.infinity,
                  height: 56,
                  child: ElevatedButton(
                    onPressed: _continueAndStartRecording,
                    style: ElevatedButton.styleFrom(
                      backgroundColor: ResponsiveHelper.purplePrimary,
                      foregroundColor: Colors.white,
                      shape: RoundedRectangleBorder(
                        borderRadius: BorderRadius.circular(16),
                      ),
                      elevation: 0,
                    ),
                    child: Text(
                      context.l10n.continueButton,
                      style: const TextStyle(
                        fontSize: 18,
                        fontWeight: FontWeight.w600,
                      ),
                    ),
                  ),
                ),
                const SizedBox(height: 24),

                // Need Help Button
                TextButton(
                  onPressed: _showHelpDialog,
                  style: TextButton.styleFrom(
                    foregroundColor: ResponsiveHelper.purplePrimary,
                    padding: const EdgeInsets.symmetric(horizontal: 24, vertical: 12),
                  ),
                  child: Text(
                    context.l10n.needHelp,
                    style: const TextStyle(
                      fontSize: 16,
                      fontWeight: FontWeight.w500,
                    ),
                  ),
                ),
              ],

              const Spacer(),
            ],
          ),
        ),
      ),
    );
  }

  Future<void> _requestPermission() async {
    setState(() {
      _isRequestingPermission = true;
    });

    try {
      await widget.connection.requestPermissionAndStartRecording();

      setState(() {
        _isRequestingPermission = false;
        _permissionRequested = true;
      });
    } catch (e) {
      setState(() {
        _isRequestingPermission = false;
      });

      AppSnackbar.showSnackbar(
        context.l10n.errorRequestingPermission(e.toString()),
        duration: const Duration(seconds: 3),
      );
    }
  }

  Future<void> _continueAndStartRecording() async {
    try {
      final bool recordingStarted = await widget.connection.checkPermissionAndStartRecording();

      if (recordingStarted) {
        AppSnackbar.showSnackbar(
          context.l10n.recordingStartedSuccessfully,
          duration: const Duration(seconds: 3),
        );

        widget.onPermissionGranted?.call();
        Navigator.of(context).pop();
      } else {
        AppSnackbar.showSnackbar(
          context.l10n.permissionNotGrantedYet,
          duration: const Duration(seconds: 5),
        );
      }
    } catch (e) {
      AppSnackbar.showSnackbar(
        context.l10n.errorStartingRecording(e.toString()),
        duration: const Duration(seconds: 3),
      );
    }
  }

  void _showHelpDialog() {
    final responsive = ResponsiveHelper(context);

    showDialog(
      context: context,
      builder: (context) => AlertDialog(
        backgroundColor: ResponsiveHelper.backgroundSecondary,
        shape: RoundedRectangleBorder(
          borderRadius: BorderRadius.circular(16),
        ),
        title: Text(
          context.l10n.needHelp,
          style: responsive.titleLarge.copyWith(fontSize: 20),
        ),
        content: Text(
          context.l10n.troubleshootingSteps,
          style: responsive.bodyMedium,
        ),
        actions: [
          TextButton(
            onPressed: () => Navigator.of(context).pop(),
            style: TextButton.styleFrom(
              foregroundColor: ResponsiveHelper.purplePrimary,
              padding: const EdgeInsets.symmetric(horizontal: 24, vertical: 12),
            ),
            child: Text(
              context.l10n.gotIt,
              style: const TextStyle(fontWeight: FontWeight.w500),
            ),
          ),
        ],
      ),
    );
  }
}
