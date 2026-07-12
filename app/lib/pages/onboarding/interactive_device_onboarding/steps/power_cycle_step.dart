import 'package:flutter/material.dart';

import 'package:provider/provider.dart';

import 'package:omi/gen/assets.gen.dart';
import 'package:omi/providers/device_onboarding_provider.dart';
import 'package:omi/pages/onboarding/interactive_device_onboarding/widgets/onboarding_step_scaffold.dart';
import 'package:omi/utils/l10n_extensions.dart';

class PowerCycleStep extends StatefulWidget {
  final VoidCallback onComplete;

  const PowerCycleStep({super.key, required this.onComplete});

  @override
  State<PowerCycleStep> createState() => _PowerCycleStepState();
}

class _PowerCycleStepState extends State<PowerCycleStep> {
  bool _showHint = false;
  bool _showContinue = false;
  bool _continueScheduled = false;

  @override
  void initState() {
    super.initState();
    final provider = context.read<DeviceOnboardingProvider>();
    provider.startPowerCycleHintTimer(() {
      if (mounted) setState(() => _showHint = true);
    });
  }

  @override
  Widget build(BuildContext context) {
    return Consumer<DeviceOnboardingProvider>(
      builder: (context, provider, _) {
        if (provider.powerCycleState == PowerCycleSubState.reconnected && !_continueScheduled) {
          _continueScheduled = true;
          Future.delayed(const Duration(seconds: 1), () {
            if (mounted) setState(() => _showContinue = true);
          });
        }

        final isOff = provider.powerCycleState == PowerCycleSubState.deviceOff ||
            provider.powerCycleState == PowerCycleSubState.waitingForReconnect;
        final isReconnected = provider.powerCycleState == PowerCycleSubState.reconnected;

        return OnboardingStepScaffold(
          title: _getTitle(provider.powerCycleState),
          subtitle: _getSubtitle(provider.powerCycleState),
          content: Column(
            children: [
              const SizedBox(height: 16),
              // Device image
              _buildDeviceImage(isConnected: !isOff),
              const SizedBox(height: 32),
              // Status card
              _buildStatusCard(provider),
              if (_showHint && provider.powerCycleState == PowerCycleSubState.waitingForOff) ...[
                const SizedBox(height: 12),
                _buildHintCard(),
              ],
              const Spacer(),
            ],
          ),
          bottomAction: _showContinue && isReconnected ? OnboardingContinueButton(onPressed: widget.onComplete) : null,
        );
      },
    );
  }

  String _getTitle(PowerCycleSubState state) {
    switch (state) {
      case PowerCycleSubState.waitingForOff:
      case PowerCycleSubState.deviceOff:
        return context.l10n.deviceOnboardingTurnOffTitle;
      case PowerCycleSubState.waitingForReconnect:
      case PowerCycleSubState.reconnected:
        return context.l10n.deviceOnboardingTurnOnTitle;
    }
  }

  String _getSubtitle(PowerCycleSubState state) {
    switch (state) {
      case PowerCycleSubState.waitingForOff:
        return context.l10n.deviceOnboardingTurnOffSubtitle;
      case PowerCycleSubState.deviceOff:
        return '';
      case PowerCycleSubState.waitingForReconnect:
        return context.l10n.deviceOnboardingTurnOnSubtitle;
      case PowerCycleSubState.reconnected:
        return '';
    }
  }

  Widget _buildDeviceImage({required bool isConnected}) {
    final pixelRatio = MediaQuery.of(context).devicePixelRatio;
    const imageSize = 180.0;

    return AnimatedSwitcher(
      duration: const Duration(milliseconds: 300),
      child: isConnected
          ? Image.asset(
              Assets.images.omiWithoutRope.path,
              key: const ValueKey('connected'),
              height: imageSize,
              width: imageSize,
              cacheHeight: (imageSize * pixelRatio).round(),
              cacheWidth: (imageSize * pixelRatio).round(),
            )
          : Stack(
              key: const ValueKey('disconnected'),
              clipBehavior: Clip.none,
              children: [
                Image.asset(
                  Assets.images.omiWithoutRopeTurnedOff.path,
                  height: imageSize,
                  width: imageSize,
                  cacheHeight: (imageSize * pixelRatio).round(),
                  cacheWidth: (imageSize * pixelRatio).round(),
                ),
                Positioned(
                  bottom: 0,
                  right: 0,
                  child: Container(
                    width: 36,
                    height: 36,
                    decoration: const BoxDecoration(shape: BoxShape.circle, color: Color(0xFFEF5350)),
                    child: const Icon(Icons.close, color: Colors.white, size: 20),
                  ),
                ),
              ],
            ),
    );
  }

  Widget _buildStatusCard(DeviceOnboardingProvider provider) {
    final state = provider.powerCycleState;

    Color statusColor;
    String statusText;
    IconData statusIcon;

    switch (state) {
      case PowerCycleSubState.waitingForOff:
        statusColor = const Color(0xFF4CAF50);
        statusText = context.l10n.deviceOnboardingStatusConnected;
        statusIcon = Icons.bluetooth_connected;
        break;
      case PowerCycleSubState.deviceOff:
        statusColor = const Color(0xFFEF5350);
        statusText = context.l10n.deviceOnboardingStatusTurningOff;
        statusIcon = Icons.power_off;
        break;
      case PowerCycleSubState.waitingForReconnect:
        statusColor = const Color(0xFFEF5350);
        statusText = context.l10n.deviceOnboardingStatusDisconnected;
        statusIcon = Icons.bluetooth_disabled;
        break;
      case PowerCycleSubState.reconnected:
        statusColor = const Color(0xFF4CAF50);
        statusText = context.l10n.deviceOnboardingStatusConnectedDone;
        statusIcon = Icons.check_circle;
        break;
    }

    return AnimatedContainer(
      duration: const Duration(milliseconds: 300),
      padding: const EdgeInsets.symmetric(horizontal: 24, vertical: 18),
      decoration: BoxDecoration(color: statusColor.withValues(alpha: 0.12), borderRadius: BorderRadius.circular(20)),
      child: Row(
        mainAxisAlignment: MainAxisAlignment.center,
        children: [
          Icon(statusIcon, color: statusColor, size: 22),
          const SizedBox(width: 12),
          Text(
            statusText,
            style: TextStyle(color: statusColor, fontSize: 18, fontWeight: FontWeight.w600),
          ),
        ],
      ),
    );
  }

  Widget _buildHintCard() {
    return Container(
      padding: const EdgeInsets.symmetric(horizontal: 20, vertical: 14),
      decoration: BoxDecoration(
        color: const Color(0xFFFFA726).withValues(alpha: 0.12),
        borderRadius: BorderRadius.circular(20),
      ),
      child: Row(
        children: [
          const Icon(Icons.info_outline, color: Color(0xFFFFA726), size: 20),
          const SizedBox(width: 12),
          Expanded(
            child: Text(
              context.l10n.deviceOnboardingHoldButtonHint,
              style: const TextStyle(color: Color(0xFFFFA726), fontSize: 14),
            ),
          ),
        ],
      ),
    );
  }
}
