import 'package:flutter/material.dart';
import 'package:provider/provider.dart';

import 'package:omi/providers/capture_provider.dart';
import 'package:omi/providers/usage_provider.dart';
import 'package:omi/services/freemium_transcription_service.dart';
import 'package:omi/utils/paywall_router.dart';

/// Handler for freemium transcription switching
/// Manages when to show the plans sheet and navigation
class FreemiumSwitchHandler {
  final FreemiumTranscriptionService _freemiumService = FreemiumTranscriptionService();

  FreemiumTranscriptionService get service => _freemiumService;

  /// Check and show plans sheet if freemium threshold reached
  /// Returns true if plans sheet was shown
  Future<bool> checkAndShowPaywall(BuildContext context, CaptureProvider captureProvider) async {
    if (_freemiumService.dialogShownThisSession) return false;

    if (!context.read<UsageProvider>().showSubscriptionUI) return false;

    if (captureProvider.freemiumThresholdReached && captureProvider.freemiumRequiresUserAction) {
      _freemiumService.markDialogShown();

      if (!context.mounted) return false;

      // Routes to either the existing PlansSheet (legacy Stripe subscribers
      // managing their plan) or the Superwall paywall (new acquisitions).
      await showUpgradePaywall(context, placement: 'transcription_minutes_exceeded');

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
