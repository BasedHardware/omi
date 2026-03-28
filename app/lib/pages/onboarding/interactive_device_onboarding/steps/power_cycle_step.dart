import 'package:flutter/material.dart';

import 'package:provider/provider.dart';

import 'package:omi/providers/device_onboarding_provider.dart';
import 'package:omi/pages/onboarding/interactive_device_onboarding/widgets/onboarding_step_scaffold.dart';

class PowerCycleStep extends StatefulWidget {
  final VoidCallback onComplete;

  const PowerCycleStep({super.key, required this.onComplete});

  @override
  State<PowerCycleStep> createState() => _PowerCycleStepState();
}

class _PowerCycleStepState extends State<PowerCycleStep> with SingleTickerProviderStateMixin {
  late AnimationController _animController;
  bool _showHint = false;
  bool _showContinue = false;

  @override
  void initState() {
    super.initState();
    _animController = AnimationController(vsync: this, duration: const Duration(milliseconds: 1000))..repeat(reverse: true);

    final provider = context.read<DeviceOnboardingProvider>();
    provider.startPowerCycleHintTimer(() {
      if (mounted) setState(() => _showHint = true);
    });
  }

  @override
  void dispose() {
    _animController.dispose();
    super.dispose();
  }

  @override
  Widget build(BuildContext context) {
    return Consumer<DeviceOnboardingProvider>(
      builder: (context, provider, _) {
        if (provider.powerCycleState == PowerCycleSubState.reconnected && !_showContinue) {
          Future.delayed(const Duration(seconds: 1), () {
            if (mounted) setState(() => _showContinue = true);
          });
        }

        return OnboardingStepScaffold(
          title: 'Turn Off & On',
          subtitle: _getSubtitle(provider.powerCycleState),
          currentStep: 2,
          content: Center(child: _buildContent(provider)),
          bottomAction: _showContinue ? OnboardingContinueButton(onPressed: widget.onComplete) : null,
        );
      },
    );
  }

  String _getSubtitle(PowerCycleSubState state) {
    switch (state) {
      case PowerCycleSubState.waitingForOff:
        return 'Hold the button for 3 seconds to turn off your Omi';
      case PowerCycleSubState.deviceOff:
        return 'Device is turning off...';
      case PowerCycleSubState.waitingForReconnect:
        return 'Now press the button to turn it back on';
      case PowerCycleSubState.reconnected:
        return 'Your Omi is back online!';
    }
  }

  Widget _buildContent(DeviceOnboardingProvider provider) {
    switch (provider.powerCycleState) {
      case PowerCycleSubState.waitingForOff:
        return _buildWaitingForOff();
      case PowerCycleSubState.deviceOff:
        return _buildDeviceOff();
      case PowerCycleSubState.waitingForReconnect:
        return _buildWaitingForReconnect();
      case PowerCycleSubState.reconnected:
        return _buildReconnected();
    }
  }

  Widget _buildWaitingForOff() {
    return Column(
      mainAxisSize: MainAxisSize.min,
      children: [
        AnimatedBuilder(
          animation: _animController,
          builder: (context, child) {
            final opacity = 0.5 + (_animController.value * 0.5);
            return Container(
              width: 100,
              height: 100,
              decoration: BoxDecoration(
                shape: BoxShape.circle,
                color: Colors.white.withValues(alpha: 0.08),
                border: Border.all(color: Colors.white.withValues(alpha: opacity), width: 2),
              ),
              child: const Icon(Icons.power_settings_new, color: Colors.white, size: 48),
            );
          },
        ),
        const SizedBox(height: 24),
        const Text('Hold the button for 3+ seconds', style: TextStyle(color: Colors.white, fontSize: 18)),
        if (_showHint) ...[
          const SizedBox(height: 16),
          Container(
            padding: const EdgeInsets.symmetric(horizontal: 16, vertical: 12),
            decoration: BoxDecoration(
              color: const Color(0xFFFFA726).withValues(alpha: 0.15),
              borderRadius: BorderRadius.circular(12),
            ),
            child: const Text(
              'Hold the button firmly until the light turns off',
              style: TextStyle(color: Color(0xFFFFA726), fontSize: 14),
              textAlign: TextAlign.center,
            ),
          ),
        ],
      ],
    );
  }

  Widget _buildDeviceOff() {
    return const Column(
      mainAxisSize: MainAxisSize.min,
      children: [
        Icon(Icons.power_off, color: Color(0xFFEF5350), size: 64),
        SizedBox(height: 16),
        Text('Device is off!', style: TextStyle(color: Color(0xFFEF5350), fontSize: 22, fontWeight: FontWeight.bold)),
      ],
    );
  }

  Widget _buildWaitingForReconnect() {
    return Column(
      mainAxisSize: MainAxisSize.min,
      children: [
        AnimatedBuilder(
          animation: _animController,
          builder: (context, child) {
            final scale = 1.0 + (_animController.value * 0.1);
            return Transform.scale(
              scale: scale,
              child: Container(
                width: 100,
                height: 100,
                decoration: BoxDecoration(
                  shape: BoxShape.circle,
                  color: const Color(0xFF4CAF50).withValues(alpha: 0.1),
                  border: Border.all(color: const Color(0xFF4CAF50).withValues(alpha: 0.5), width: 2),
                ),
                child: const Icon(Icons.power_settings_new, color: Color(0xFF4CAF50), size: 48),
              ),
            );
          },
        ),
        const SizedBox(height: 24),
        const Text('Press the button to turn it on', style: TextStyle(color: Colors.white, fontSize: 18)),
      ],
    );
  }

  Widget _buildReconnected() {
    return const Column(
      mainAxisSize: MainAxisSize.min,
      children: [
        Icon(Icons.check_circle, color: Color(0xFF4CAF50), size: 64),
        SizedBox(height: 16),
        Text('Connected!', style: TextStyle(color: Color(0xFF4CAF50), fontSize: 22, fontWeight: FontWeight.bold)),
      ],
    );
  }
}
