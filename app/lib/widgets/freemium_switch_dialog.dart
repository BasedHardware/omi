import 'package:flutter/material.dart';
import 'package:omi/backend/preferences.dart';
import 'package:omi/pages/settings/transcription_settings_page.dart';
import 'package:omi/providers/capture_provider.dart';
import 'package:omi/services/freemium_transcription_service.dart';
import 'package:provider/provider.dart';

/// Handler for freemium transcription switching
/// Manages the dialog display and auto-switch logic
class FreemiumSwitchHandler {
  final FreemiumTranscriptionService _freemiumService = FreemiumTranscriptionService();

  FreemiumTranscriptionService get service => _freemiumService;

  /// Check and show appropriate dialog based on freemium state
  /// Returns true if a dialog was shown
  Future<bool> checkAndShowDialog(BuildContext context, CaptureProvider captureProvider) async {
    if (_freemiumService.dialogShownThisSession) return false;

    if (captureProvider.freemiumThresholdReached && captureProvider.freemiumRequiresUserAction) {
      _freemiumService.markDialogShown();

      // Check if on-device STT is ready for auto-switch (async check for model files)
      final readiness = await _freemiumService.checkReadiness();

      if (!context.mounted) return false;

      if (readiness == FreemiumReadiness.ready) {
        _showAutoSwitchDialog(context, captureProvider.freemiumRemainingSeconds);
      } else {
        _showManualSetupDialog(context, captureProvider.freemiumRemainingSeconds);
      }
      return true;
    }
    return false;
  }

  /// Show auto-switch countdown dialog when on-device STT is ready
  void _showAutoSwitchDialog(BuildContext context, int remainingSeconds) {
    final minutes = (remainingSeconds / 60).ceil();
    final timeText = minutes > 0 ? '$minutes minute${minutes != 1 ? 's' : ''}' : 'less than a minute';

    // Start the countdown
    _freemiumService.startAutoSwitchCountdown(seconds: 10);

    // Set up auto-switch callback (don't close dialog, let it show confirmation)
    _freemiumService.onAutoSwitch = () {
      _performFreemiumSwitch(context);
    };

    showModalBottomSheet(
      context: context,
      backgroundColor: Colors.transparent,
      isScrollControlled: true,
      isDismissible: false,
      enableDrag: false,
      builder: (dialogContext) => FreemiumAutoSwitchDialog(
        timeText: timeText,
        freemiumService: _freemiumService,
        onStayOnPremium: () {
          _freemiumService.cancelCountdown();
          Navigator.pop(dialogContext);
        },
        onSwitchNow: () {
          _freemiumService.switchToFreeNow();
        },
        onDismiss: () {
          Navigator.pop(dialogContext);
        },
      ),
    );
  }

  /// Show manual setup dialog when on-device STT is not ready
  void _showManualSetupDialog(BuildContext context, int remainingSeconds) {
    final minutes = (remainingSeconds / 60).ceil();
    final timeText = minutes > 0 ? '$minutes minute${minutes != 1 ? 's' : ''}' : 'less than a minute';

    showModalBottomSheet(
      context: context,
      backgroundColor: Colors.transparent,
      isScrollControlled: true,
      builder: (dialogContext) => FreemiumManualSetupDialog(
        timeText: timeText,
        onSetup: () {
          Navigator.pop(dialogContext);
          Navigator.push(
            context,
            MaterialPageRoute(
              builder: (context) => const TranscriptionSettingsPage(),
            ),
          );
        },
        onLater: () => Navigator.pop(dialogContext),
      ),
    );
  }

  /// Perform the actual switch to freemium (on-device) STT
  Future<void> _performFreemiumSwitch(BuildContext context) async {
    if (!context.mounted) return;

    final captureProvider = Provider.of<CaptureProvider>(context, listen: false);
    final freemiumConfig = _freemiumService.getFreemiumConfig();

    if (freemiumConfig != null) {
      debugPrint('[Freemium] Auto-switching to on-device STT');
      // Save the freemium config and reconnect
      await SharedPreferencesUtil().saveCustomSttConfig(freemiumConfig);
      // Force reconnect with new config
      captureProvider.onRecordProfileSettingChanged();
    }
  }

  /// Clean up resources
  void dispose() {
    _freemiumService.cancelCountdown();
    _freemiumService.onAutoSwitch = null;
  }

  /// Reset for new session (call when recording starts)
  void resetSession() {
    _freemiumService.resetDialogShownFlag();
    _freemiumService.reset();
  }

  /// Reset just the dialog shown flag (for threshold state reset)
  void resetDialogFlag() {
    _freemiumService.resetDialogShownFlag();
  }
}

/// Auto-switch countdown dialog widget
class FreemiumAutoSwitchDialog extends StatefulWidget {
  final String timeText;
  final FreemiumTranscriptionService freemiumService;
  final VoidCallback onStayOnPremium;
  final VoidCallback onSwitchNow;
  final VoidCallback onDismiss;

  const FreemiumAutoSwitchDialog({
    super.key,
    required this.timeText,
    required this.freemiumService,
    required this.onStayOnPremium,
    required this.onSwitchNow,
    required this.onDismiss,
  });

  @override
  State<FreemiumAutoSwitchDialog> createState() => _FreemiumAutoSwitchDialogState();
}

class _FreemiumAutoSwitchDialogState extends State<FreemiumAutoSwitchDialog> {
  bool _hasSwitched = false;

  @override
  void initState() {
    super.initState();
    widget.freemiumService.addListener(_onServiceUpdate);
  }

  @override
  void dispose() {
    widget.freemiumService.removeListener(_onServiceUpdate);
    super.dispose();
  }

  void _onServiceUpdate() {
    if (mounted) {
      // Check if switch has completed
      if (widget.freemiumService.isUsingFreeStt && !_hasSwitched) {
        setState(() {
          _hasSwitched = true;
        });
      } else {
        setState(() {});
      }
    }
  }

  @override
  Widget build(BuildContext context) {
    final countdown = widget.freemiumService.countdownSeconds;

    return Container(
      decoration: const BoxDecoration(
        color: Color(0xFF1A1A1A),
        borderRadius: BorderRadius.vertical(top: Radius.circular(20)),
      ),
      padding: const EdgeInsets.all(24),
      child: SafeArea(
        child: _hasSwitched ? _buildSwitchedContent() : _buildCountdownContent(countdown),
      ),
    );
  }

  Widget _buildCountdownContent(int countdown) {
    return Column(
      mainAxisSize: MainAxisSize.min,
      children: [
        Container(
          width: 40,
          height: 4,
          margin: const EdgeInsets.only(bottom: 24),
          decoration: BoxDecoration(
            color: Colors.grey.shade700,
            borderRadius: BorderRadius.circular(2),
          ),
        ),
        const Text(
          'Switching to On-Device Transcription',
          style: TextStyle(
            color: Colors.white,
            fontSize: 18,
            fontWeight: FontWeight.w600,
          ),
          textAlign: TextAlign.center,
        ),
        const SizedBox(height: 12),
        Text(
          'You have ${widget.timeText} of premium minutes remaining. '
          'Switching to free on-device transcription to continue without interruption.',
          style: TextStyle(
            color: Colors.grey.shade400,
            fontSize: 14,
            height: 1.5,
          ),
          textAlign: TextAlign.center,
        ),
        const SizedBox(height: 24),
        // Primary action with countdown
        SizedBox(
          width: double.infinity,
          child: ElevatedButton(
            onPressed: widget.onSwitchNow,
            style: ElevatedButton.styleFrom(
              backgroundColor: Colors.white,
              foregroundColor: Colors.black,
              padding: const EdgeInsets.symmetric(vertical: 14),
              shape: RoundedRectangleBorder(
                borderRadius: BorderRadius.circular(12),
              ),
            ),
            child: Text(
              'Switch Now ($countdown)',
              style: const TextStyle(
                fontSize: 15,
                fontWeight: FontWeight.w600,
              ),
            ),
          ),
        ),
        const SizedBox(height: 12),
        // Cancel action
        TextButton(
          onPressed: widget.onStayOnPremium,
          child: Text(
            'Cancel',
            style: TextStyle(
              color: Colors.grey.shade500,
              fontSize: 14,
            ),
          ),
        ),
      ],
    );
  }

  Widget _buildSwitchedContent() {
    return Column(
      mainAxisSize: MainAxisSize.min,
      children: [
        Container(
          width: 40,
          height: 4,
          margin: const EdgeInsets.only(bottom: 24),
          decoration: BoxDecoration(
            color: Colors.grey.shade700,
            borderRadius: BorderRadius.circular(2),
          ),
        ),
        Container(
          width: 48,
          height: 48,
          decoration: BoxDecoration(
            shape: BoxShape.circle,
            color: Colors.black.withOpacity(0.15),
          ),
          child: const Icon(
            Icons.check,
            color: Colors.white,
            size: 28,
          ),
        ),
        const SizedBox(height: 16),
        const Text(
          'Switched to On-Device Transcription',
          style: TextStyle(
            color: Colors.white,
            fontSize: 18,
            fontWeight: FontWeight.w600,
          ),
          textAlign: TextAlign.center,
        ),
        const SizedBox(height: 12),
        Text(
          'You\'re now using free unlimited on-device transcription. Your conversation continues without interruption.',
          style: TextStyle(
            color: Colors.grey.shade400,
            fontSize: 14,
            height: 1.5,
          ),
          textAlign: TextAlign.center,
        ),
        const SizedBox(height: 24),
        SizedBox(
          width: double.infinity,
          child: ElevatedButton(
            onPressed: widget.onDismiss,
            style: ElevatedButton.styleFrom(
              backgroundColor: Colors.white,
              foregroundColor: Colors.black,
              padding: const EdgeInsets.symmetric(vertical: 14),
              shape: RoundedRectangleBorder(
                borderRadius: BorderRadius.circular(12),
              ),
            ),
            child: const Text(
              'Got it',
              style: TextStyle(
                fontSize: 15,
                fontWeight: FontWeight.w600,
              ),
            ),
          ),
        ),
      ],
    );
  }
}

/// Manual setup dialog widget (shown when on-device STT is not ready)
class FreemiumManualSetupDialog extends StatelessWidget {
  final String timeText;
  final VoidCallback onSetup;
  final VoidCallback onLater;

  const FreemiumManualSetupDialog({
    super.key,
    required this.timeText,
    required this.onSetup,
    required this.onLater,
  });

  @override
  Widget build(BuildContext context) {
    return Container(
      decoration: const BoxDecoration(
        color: Color(0xFF1A1A1A),
        borderRadius: BorderRadius.vertical(top: Radius.circular(20)),
      ),
      padding: const EdgeInsets.all(24),
      child: SafeArea(
        child: Column(
          mainAxisSize: MainAxisSize.min,
          children: [
            Container(
              width: 40,
              height: 4,
              margin: const EdgeInsets.only(bottom: 24),
              decoration: BoxDecoration(
                color: Colors.grey.shade700,
                borderRadius: BorderRadius.circular(2),
              ),
            ),
            const Text(
              'Premium Minutes Running Low',
              style: TextStyle(
                color: Colors.white,
                fontSize: 18,
                fontWeight: FontWeight.w600,
              ),
              textAlign: TextAlign.center,
            ),
            const SizedBox(height: 12),
            Text(
              'You have $timeText of premium minutes left. Omi is free forever—setup on-device transcription for unlimited minutes.',
              style: TextStyle(
                color: Colors.grey.shade400,
                fontSize: 14,
                height: 1.5,
              ),
              textAlign: TextAlign.center,
            ),
            const SizedBox(height: 24),
            SizedBox(
              width: double.infinity,
              child: ElevatedButton(
                onPressed: onSetup,
                style: ElevatedButton.styleFrom(
                  backgroundColor: Colors.white,
                  foregroundColor: Colors.black,
                  padding: const EdgeInsets.symmetric(vertical: 14),
                  shape: RoundedRectangleBorder(
                    borderRadius: BorderRadius.circular(12),
                  ),
                ),
                child: const Text(
                  'Get Unlimited Free',
                  style: TextStyle(
                    fontSize: 15,
                    fontWeight: FontWeight.w600,
                  ),
                ),
              ),
            ),
            const SizedBox(height: 8),
            TextButton(
              onPressed: onLater,
              child: Text(
                'Later',
                style: TextStyle(
                  color: Colors.grey.shade500,
                  fontSize: 14,
                ),
              ),
            ),
          ],
        ),
      ),
    );
  }
}
