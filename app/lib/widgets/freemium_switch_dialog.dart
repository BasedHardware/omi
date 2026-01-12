import 'package:flutter/material.dart';
import 'package:omi/providers/capture_provider.dart';
import 'package:omi/services/freemium_transcription_service.dart';
import 'package:omi/widgets/freemium_paywall_page.dart';

/// Handler for freemium transcription switching
/// Manages when to show the paywall and navigation
class FreemiumSwitchHandler {
  final FreemiumTranscriptionService _freemiumService = FreemiumTranscriptionService();

  FreemiumTranscriptionService get service => _freemiumService;

  /// Check and show paywall if freemium threshold reached
  /// Returns true if paywall was shown
  Future<bool> checkAndShowPaywall(BuildContext context, CaptureProvider captureProvider) async {
    if (_freemiumService.dialogShownThisSession) return false;

    if (captureProvider.freemiumThresholdReached && captureProvider.freemiumRequiresUserAction) {
      _freemiumService.markDialogShown();

      // Check on-device readiness
      final readiness = await _freemiumService.checkReadiness();
      final isOnDeviceReady = readiness == FreemiumReadiness.ready;

      if (!context.mounted) return false;

      // Navigate to full-screen paywall
      await Navigator.of(context).push<bool>(
        MaterialPageRoute(
          builder: (context) => FreemiumPaywallPage(
            remainingSeconds: captureProvider.freemiumRemainingSeconds,
            isOnDeviceReady: isOnDeviceReady,
          ),
          fullscreenDialog: true,
        ),
      );

      // result == true means user upgraded
      // result == false means user chose on-device
      // result == null means user dismissed
      return true;
    }
    return false;
  }

  /// Legacy method name for backward compatibility
  Future<bool> checkAndShowDialog(BuildContext context, CaptureProvider captureProvider) async {
    return checkAndShowPaywall(context, captureProvider);
  }

  /// Clean up resources
  void dispose() {
    _freemiumService.onAutoSwitch = null;
  }

  /// Reset for new session (call when recording starts)
  void resetSession() {
    _freemiumService.resetDialogShownFlag();
    _freemiumService.reset();
  }

  /// Reset just the dialog shown flag
  void resetDialogFlag() {
    _freemiumService.resetDialogShownFlag();
  }
}
