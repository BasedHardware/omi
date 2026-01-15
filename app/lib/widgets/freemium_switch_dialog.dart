import 'package:flutter/material.dart';

import 'package:omi/pages/settings/widgets/plans_sheet.dart';
import 'package:omi/providers/capture_provider.dart';
import 'package:omi/services/freemium_transcription_service.dart';

/// Handler for freemium transcription switching
/// Manages when to show the plans sheet and navigation
class FreemiumSwitchHandler {
  final FreemiumTranscriptionService _freemiumService = FreemiumTranscriptionService();

  FreemiumTranscriptionService get service => _freemiumService;

  /// Check and show plans sheet if freemium threshold reached
  /// Returns true if plans sheet was shown
  Future<bool> checkAndShowPaywall(BuildContext context, CaptureProvider captureProvider) async {
    if (_freemiumService.dialogShownThisSession) return false;

    if (captureProvider.freemiumThresholdReached && captureProvider.freemiumRequiresUserAction) {
      _freemiumService.markDialogShown();

      if (!context.mounted) return false;

      // Show plans sheet directly
      await showModalBottomSheet(
        context: context,
        isScrollControlled: true,
        backgroundColor: Colors.black,
        builder: (sheetContext) => _PlansSheetWrapper(),
      );

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

/// Wrapper widget to create animation controllers for PlansSheet
class _PlansSheetWrapper extends StatefulWidget {
  @override
  State<_PlansSheetWrapper> createState() => _PlansSheetWrapperState();
}

class _PlansSheetWrapperState extends State<_PlansSheetWrapper> with TickerProviderStateMixin {
  late AnimationController _waveController;
  late AnimationController _arrowController;
  late Animation<double> _arrowAnimation;

  @override
  void initState() {
    super.initState();
    _waveController = AnimationController(
      duration: const Duration(milliseconds: 18000),
      vsync: this,
    )..repeat();

    _arrowController = AnimationController(
      duration: const Duration(milliseconds: 800),
      vsync: this,
    )..repeat(reverse: true);

    _arrowAnimation = Tween<double>(begin: 0, end: 3).animate(
      CurvedAnimation(parent: _arrowController, curve: Curves.easeInOut),
    );
  }

  @override
  void dispose() {
    _waveController.dispose();
    _arrowController.dispose();
    super.dispose();
  }

  @override
  Widget build(BuildContext context) {
    return PlansSheet(
      waveController: _waveController,
      notesController: _waveController,
      arrowController: _arrowController,
      arrowAnimation: _arrowAnimation,
    );
  }
}
