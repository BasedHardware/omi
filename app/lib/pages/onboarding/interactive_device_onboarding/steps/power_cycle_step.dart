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
          subtitle: '',
          currentStep: 2,
          content: Column(
            children: [
              const Spacer(flex: 1),
              _buildStatusCard(provider),
              const SizedBox(height: 16),
              _buildInstructionCard(provider),
              if (_showHint && provider.powerCycleState == PowerCycleSubState.waitingForOff) ...[
                const SizedBox(height: 12),
                _buildHintCard(),
              ],
              const Spacer(flex: 2),
            ],
          ),
          bottomAction: _showContinue ? OnboardingContinueButton(onPressed: widget.onComplete) : null,
        );
      },
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
        statusText = 'Connected';
        statusIcon = Icons.bluetooth_connected;
        break;
      case PowerCycleSubState.deviceOff:
        statusColor = const Color(0xFFEF5350);
        statusText = 'Turning off...';
        statusIcon = Icons.power_off;
        break;
      case PowerCycleSubState.waitingForReconnect:
        statusColor = const Color(0xFFEF5350);
        statusText = 'Disconnected';
        statusIcon = Icons.bluetooth_disabled;
        break;
      case PowerCycleSubState.reconnected:
        statusColor = const Color(0xFF4CAF50);
        statusText = 'Connected!';
        statusIcon = Icons.check_circle;
        break;
    }

    return AnimatedContainer(
      duration: const Duration(milliseconds: 300),
      padding: const EdgeInsets.symmetric(horizontal: 24, vertical: 20),
      decoration: BoxDecoration(
        color: statusColor.withValues(alpha: 0.12),
        borderRadius: BorderRadius.circular(20),
      ),
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

  Widget _buildInstructionCard(DeviceOnboardingProvider provider) {
    final state = provider.powerCycleState;

    String instruction;
    IconData icon;

    switch (state) {
      case PowerCycleSubState.waitingForOff:
        instruction = 'Hold the button for 3+ seconds to turn off';
        icon = Icons.power_settings_new;
        break;
      case PowerCycleSubState.deviceOff:
        instruction = 'Device is turning off...';
        icon = Icons.power_settings_new;
        break;
      case PowerCycleSubState.waitingForReconnect:
        instruction = 'Press the button to turn it back on';
        icon = Icons.power_settings_new;
        break;
      case PowerCycleSubState.reconnected:
        instruction = 'Your Omi is back online!';
        icon = Icons.celebration;
        break;
    }

    return Container(
      padding: const EdgeInsets.symmetric(horizontal: 20, vertical: 16),
      decoration: BoxDecoration(
        color: Colors.white.withValues(alpha: 0.06),
        borderRadius: BorderRadius.circular(20),
      ),
      child: Row(
        children: [
          Icon(icon, color: Colors.white.withValues(alpha: 0.6), size: 22),
          const SizedBox(width: 14),
          Expanded(
            child: Text(
              instruction,
              style: const TextStyle(color: Colors.white, fontSize: 15),
            ),
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
      child: const Row(
        children: [
          Icon(Icons.info_outline, color: Color(0xFFFFA726), size: 20),
          SizedBox(width: 12),
          Expanded(
            child: Text(
              'Hold the button firmly until the light turns off',
              style: TextStyle(color: Color(0xFFFFA726), fontSize: 14),
            ),
          ),
        ],
      ),
    );
  }
}
