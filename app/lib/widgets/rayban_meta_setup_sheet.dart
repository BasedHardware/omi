import 'dart:async';

import 'package:flutter/material.dart';

import 'package:omi/gen/assets.gen.dart';
import 'package:omi/gen/pigeon_communicator.g.dart';
import 'package:omi/utils/l10n_extensions.dart';
import 'package:omi/utils/logger.dart';
import 'package:omi/utils/responsive/responsive_helper.dart';

/// Guided setup for Ray-Ban Meta glasses.
///
/// Walks the user through whatever is still missing, in plain language:
/// Meta AI authorization (full mode), glasses camera permission, or — on
/// builds without the Meta toolkit — an honest explanation of audio-only
/// mode. Pops with `true` when the glasses are ready to connect.
class RayBanMetaSetupSheet extends StatefulWidget {
  const RayBanMetaSetupSheet({super.key});

  /// Returns true when setup finished and the device is ready to connect.
  static Future<bool> show(BuildContext context) async {
    final ready = await showModalBottomSheet<bool>(
      context: context,
      isScrollControlled: true,
      backgroundColor: Colors.transparent,
      builder: (_) => const RayBanMetaSetupSheet(),
    );
    return ready == true;
  }

  @override
  State<RayBanMetaSetupSheet> createState() => _RayBanMetaSetupSheetState();
}

enum _SetupStep { loading, audioOnly, register, waitingForMetaAi, cameraPermission, ready }

class _RayBanMetaSetupSheetState extends State<RayBanMetaSetupSheet> {
  final RayBanMetaHostAPI _host = RayBanMetaHostAPI();
  _SetupStep _step = _SetupStep.loading;
  Timer? _registrationPoll;
  bool _refreshing = false;
  bool _completed = false;

  @override
  void initState() {
    super.initState();
    _refreshStep();
  }

  @override
  void dispose() {
    _registrationPoll?.cancel();
    super.dispose();
  }

  Future<void> _refreshStep() async {
    if (_refreshing || _completed) return;
    _refreshing = true;
    try {
      final mode = await _host.getAvailabilityMode();
      if (mode != 'full') {
        _setStep(_SetupStep.audioOnly);
        return;
      }
      final registration = await _host.getRegistrationState();
      if (registration != 'registered') {
        _setStep(_step == _SetupStep.waitingForMetaAi ? _SetupStep.waitingForMetaAi : _SetupStep.register);
        return;
      }
      _registrationPoll?.cancel();
      final camera = await _host.getCameraPermissionStatus();
      if (camera != 'granted') {
        _setStep(_SetupStep.cameraPermission);
        return;
      }
      _setStep(_SetupStep.ready);
    } catch (e) {
      Logger.debug('Ray-Ban Meta setup: state refresh failed: $e');
      _setStep(_SetupStep.audioOnly);
    } finally {
      _refreshing = false;
    }
  }

  void _setStep(_SetupStep step) {
    if (!mounted) return;
    setState(() => _step = step);
    if (step == _SetupStep.ready && !_completed) {
      _completed = true;
      _registrationPoll?.cancel();
      Navigator.of(context).pop(true);
    }
  }

  Future<void> _startRegistration() async {
    try {
      await _host.startRegistration();
      _setStep(_SetupStep.waitingForMetaAi);
      // The Meta AI app takes over; poll until its callback lands.
      _registrationPoll?.cancel();
      _registrationPoll = Timer.periodic(const Duration(seconds: 2), (_) => _refreshStep());
    } catch (e) {
      Logger.debug('Ray-Ban Meta setup: registration failed: $e');
    }
  }

  Future<void> _requestCameraPermission() async {
    try {
      await _host.requestCameraPermission();
    } catch (e) {
      Logger.debug('Ray-Ban Meta setup: camera permission failed: $e');
    }
    await _refreshStep();
  }

  @override
  Widget build(BuildContext context) {
    final responsive = ResponsiveHelper(context);

    return Container(
      decoration: const BoxDecoration(
        color: ResponsiveHelper.backgroundSecondary,
        borderRadius: BorderRadius.only(topLeft: Radius.circular(24), topRight: Radius.circular(24)),
      ),
      child: SafeArea(
        child: Column(
          mainAxisSize: MainAxisSize.min,
          children: [
            Container(
              margin: const EdgeInsets.only(top: 12),
              width: 40,
              height: 4,
              decoration: BoxDecoration(color: ResponsiveHelper.textTertiary, borderRadius: BorderRadius.circular(2)),
            ),
            Padding(
              padding: const EdgeInsets.all(32.0),
              child: Column(
                children: [
                  Container(
                    height: 120,
                    width: 120,
                    decoration: BoxDecoration(
                      borderRadius: BorderRadius.circular(20),
                      boxShadow: responsive.mediumShadow,
                      color: Colors.white,
                    ),
                    child: ClipRRect(
                      borderRadius: BorderRadius.circular(20),
                      child: Padding(
                        padding: const EdgeInsets.all(12.0),
                        child: Image.asset(Assets.images.raybanMeta.path, fit: BoxFit.contain),
                      ),
                    ),
                  ),
                  const SizedBox(height: 32),
                  ..._buildStepContent(context, responsive),
                ],
              ),
            ),
          ],
        ),
      ),
    );
  }

  List<Widget> _buildStepContent(BuildContext context, ResponsiveHelper responsive) {
    switch (_step) {
      case _SetupStep.loading:
      case _SetupStep.ready:
        return [
          Text(context.l10n.connectRayBanMeta, style: responsive.titleLarge, textAlign: TextAlign.center),
          const SizedBox(height: 24),
          const CircularProgressIndicator(valueColor: AlwaysStoppedAnimation<Color>(Colors.white), strokeWidth: 2),
        ];

      case _SetupStep.audioOnly:
        return [
          Text(context.l10n.raybanMetaAudioOnlyTitle,
              style: responsive.titleLarge.copyWith(height: 1.2), textAlign: TextAlign.center),
          const SizedBox(height: 16),
          Text(context.l10n.raybanMetaAudioOnlyExplanation, style: responsive.bodyLarge, textAlign: TextAlign.center),
          const SizedBox(height: 12),
          Text(context.l10n.raybanMetaMusicPauseNote,
              style: responsive.bodyMedium.copyWith(color: ResponsiveHelper.textTertiary), textAlign: TextAlign.center),
          const SizedBox(height: 32),
          _primaryButton(context.l10n.raybanMetaContinue, () => Navigator.of(context).pop(true)),
          const SizedBox(height: 12),
          _secondaryButton(context.l10n.cancel, () => Navigator.of(context).pop(false)),
        ];

      case _SetupStep.register:
        return [
          Text(context.l10n.connectRayBanMeta,
              style: responsive.titleLarge.copyWith(height: 1.2), textAlign: TextAlign.center),
          const SizedBox(height: 16),
          Text(context.l10n.raybanMetaSetupDescription, style: responsive.bodyLarge, textAlign: TextAlign.center),
          const SizedBox(height: 32),
          _primaryButton(context.l10n.raybanMetaOpenMetaAI, _startRegistration),
          const SizedBox(height: 12),
          _secondaryButton(context.l10n.cancel, () => Navigator.of(context).pop(false)),
        ];

      case _SetupStep.waitingForMetaAi:
        return [
          Text(context.l10n.connectRayBanMeta,
              style: responsive.titleLarge.copyWith(height: 1.2), textAlign: TextAlign.center),
          const SizedBox(height: 16),
          Text(context.l10n.raybanMetaWaitingForMetaAI, style: responsive.bodyLarge, textAlign: TextAlign.center),
          const SizedBox(height: 24),
          const CircularProgressIndicator(valueColor: AlwaysStoppedAnimation<Color>(Colors.white), strokeWidth: 2),
          const SizedBox(height: 24),
          _secondaryButton(context.l10n.raybanMetaCheckAgain, _refreshStep),
        ];

      case _SetupStep.cameraPermission:
        return [
          Text(context.l10n.raybanMetaAllowCamera,
              style: responsive.titleLarge.copyWith(height: 1.2), textAlign: TextAlign.center),
          const SizedBox(height: 16),
          Text(context.l10n.raybanMetaCameraExplanation, style: responsive.bodyLarge, textAlign: TextAlign.center),
          const SizedBox(height: 32),
          _primaryButton(context.l10n.raybanMetaAllowCamera, _requestCameraPermission),
          const SizedBox(height: 12),
          _secondaryButton(context.l10n.raybanMetaSkipForNow, () => Navigator.of(context).pop(true)),
        ];
    }
  }

  Widget _primaryButton(String label, VoidCallback onPressed) {
    return SizedBox(
      width: double.infinity,
      height: 52,
      child: ElevatedButton(
        onPressed: onPressed,
        style: ElevatedButton.styleFrom(
          backgroundColor: Colors.white,
          foregroundColor: Colors.black,
          shape: RoundedRectangleBorder(borderRadius: BorderRadius.circular(16)),
        ),
        child: Text(label, style: const TextStyle(fontSize: 16, fontWeight: FontWeight.w600)),
      ),
    );
  }

  Widget _secondaryButton(String label, VoidCallback onPressed) {
    return SizedBox(
      width: double.infinity,
      height: 52,
      child: TextButton(
        onPressed: onPressed,
        child: Text(
          label,
          style: const TextStyle(fontSize: 16, color: ResponsiveHelper.textTertiary),
        ),
      ),
    );
  }
}
