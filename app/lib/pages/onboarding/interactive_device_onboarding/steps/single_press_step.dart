import 'package:flutter/material.dart';

import 'package:provider/provider.dart';

import 'package:omi/backend/schema/message.dart';
import 'package:omi/providers/device_onboarding_provider.dart';
import 'package:omi/providers/message_provider.dart';
import 'package:omi/pages/onboarding/interactive_device_onboarding/widgets/onboarding_step_scaffold.dart';

class SinglePressStep extends StatefulWidget {
  final VoidCallback onComplete;

  const SinglePressStep({super.key, required this.onComplete});

  @override
  State<SinglePressStep> createState() => _SinglePressStepState();
}

class _SinglePressStepState extends State<SinglePressStep> with SingleTickerProviderStateMixin {
  late AnimationController _pulseController;
  bool _showContinue = false;
  int _previousMessageCount = 0;

  @override
  void initState() {
    super.initState();
    _pulseController = AnimationController(vsync: this, duration: const Duration(milliseconds: 1200))..repeat(reverse: true);
    _previousMessageCount = context.read<MessageProvider>().messages.length;
    context.read<MessageProvider>().addListener(_onMessagesChanged);
  }

  void _onMessagesChanged() {
    final messageProvider = context.read<MessageProvider>();
    final onboardingProvider = context.read<DeviceOnboardingProvider>();

    if (messageProvider.messages.length > _previousMessageCount && onboardingProvider.questionSent) {
      final latestMessage = messageProvider.messages.last;
      if (latestMessage.sender == MessageSender.ai) {
        onboardingProvider.onVoiceResponseReceived(latestMessage.text);
        setState(() => _showContinue = true);
      }
    }
    _previousMessageCount = messageProvider.messages.length;
  }

  @override
  void dispose() {
    _pulseController.dispose();
    context.read<MessageProvider>().removeListener(_onMessagesChanged);
    super.dispose();
  }

  @override
  Widget build(BuildContext context) {
    return Consumer<DeviceOnboardingProvider>(
      builder: (context, provider, _) {
        return OnboardingStepScaffold(
          title: 'Ask Omi a Question',
          subtitle: 'Press the button once, speak your question, then press again when done',
          currentStep: 1,
          content: Center(
            child: Column(
              mainAxisAlignment: MainAxisAlignment.center,
              children: [
                _buildStatusContent(provider),
              ],
            ),
          ),
          bottomAction: _showContinue ? OnboardingContinueButton(onPressed: widget.onComplete) : null,
        );
      },
    );
  }

  Widget _buildStatusContent(DeviceOnboardingProvider provider) {
    if (provider.aiResponse != null) {
      return Column(
        children: [
          const Icon(Icons.check_circle, color: Color(0xFF4CAF50), size: 48),
          const SizedBox(height: 16),
          Container(
            padding: const EdgeInsets.all(20),
            decoration: BoxDecoration(
              color: Colors.white.withValues(alpha: 0.08),
              borderRadius: BorderRadius.circular(16),
            ),
            child: Text(
              provider.aiResponse!,
              style: const TextStyle(color: Colors.white, fontSize: 16, height: 1.4),
              textAlign: TextAlign.center,
              maxLines: 8,
              overflow: TextOverflow.ellipsis,
            ),
          ),
        ],
      );
    }

    if (provider.questionSent) {
      return const Column(
        children: [
          SizedBox(width: 48, height: 48, child: CircularProgressIndicator(color: Colors.white, strokeWidth: 3)),
          SizedBox(height: 16),
          Text('Processing...', style: TextStyle(color: Colors.white, fontSize: 18)),
        ],
      );
    }

    if (provider.voiceSessionActive) {
      return Column(
        children: [
          _buildListeningIndicator(),
          const SizedBox(height: 16),
          const Text('Listening...', style: TextStyle(color: Colors.white, fontSize: 20, fontWeight: FontWeight.w600)),
          const SizedBox(height: 8),
          const Text(
            'Speak your question, then press the button again',
            style: TextStyle(color: Color(0xFF9E9E9E), fontSize: 14),
            textAlign: TextAlign.center,
          ),
        ],
      );
    }

    // Waiting for button press
    return Column(
      children: [
        AnimatedBuilder(
          animation: _pulseController,
          builder: (context, child) {
            final opacity = 0.5 + (_pulseController.value * 0.5);
            return Container(
              width: 100,
              height: 100,
              decoration: BoxDecoration(
                shape: BoxShape.circle,
                color: Colors.white.withValues(alpha: 0.08),
                border: Border.all(color: Colors.white.withValues(alpha: opacity), width: 2),
              ),
              child: Icon(Icons.touch_app, color: Colors.white.withValues(alpha: opacity), size: 48),
            );
          },
        ),
        const SizedBox(height: 24),
        const Text('Press the button on your Omi', style: TextStyle(color: Colors.white, fontSize: 18)),
      ],
    );
  }

  Widget _buildListeningIndicator() {
    return AnimatedBuilder(
      animation: _pulseController,
      builder: (context, child) {
        final scale = 1.0 + (_pulseController.value * 0.2);
        return Transform.scale(
          scale: scale,
          child: Container(
            width: 80,
            height: 80,
            decoration: BoxDecoration(
              shape: BoxShape.circle,
              color: const Color(0xFF4CAF50).withValues(alpha: 0.2),
              border: Border.all(color: const Color(0xFF4CAF50), width: 2),
            ),
            child: const Icon(Icons.mic, color: Color(0xFF4CAF50), size: 40),
          ),
        );
      },
    );
  }
}
