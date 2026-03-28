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

String _stripMarkdown(String text) {
  return text
      .replaceAllMapped(RegExp(r'\*\*(.+?)\*\*'), (m) => m[1]!) // bold
      .replaceAllMapped(RegExp(r'\*(.+?)\*'), (m) => m[1]!) // italic
      .replaceAllMapped(RegExp(r'__(.+?)__'), (m) => m[1]!) // bold alt
      .replaceAllMapped(RegExp(r'_(.+?)_'), (m) => m[1]!) // italic alt
      .replaceAllMapped(RegExp(r'~~(.+?)~~'), (m) => m[1]!) // strikethrough
      .replaceAllMapped(RegExp(r'`(.+?)`'), (m) => m[1]!); // inline code
}

class _SinglePressStepState extends State<SinglePressStep> with SingleTickerProviderStateMixin {
  late AnimationController _pulseController;
  late MessageProvider _messageProvider;
  bool _showContinue = false;

  // Snapshot of message count when step loads, to find only messages from this interaction
  late int _messageCountAtStart;
  String? _userQuestion;
  String? _aiResponse;

  @override
  void initState() {
    super.initState();
    _pulseController = AnimationController(vsync: this, duration: const Duration(milliseconds: 1200))..repeat(reverse: true);
    _messageProvider = context.read<MessageProvider>();
    _messageCountAtStart = _messageProvider.messages.length;
    _messageProvider.addListener(_onMessagesChanged);
  }

  void _onMessagesChanged() {
    if (!mounted || _aiResponse != null) return;

    final onboardingProvider = context.read<DeviceOnboardingProvider>();
    if (!onboardingProvider.questionSent) return;

    // Look through messages added since this step loaded
    if (_messageProvider.messages.length <= _messageCountAtStart) return;
    final newMessages = _messageProvider.messages.sublist(_messageCountAtStart);

    // Find the user's question (human message from the voice command)
    for (final msg in newMessages) {
      if (msg.sender == MessageSender.human && _userQuestion == null) {
        _userQuestion = msg.text;
      }
    }

    // Find the AI response — must be non-empty, finalized (not placeholder), and not from an app integration
    for (final msg in newMessages) {
      if (msg.sender == MessageSender.ai && msg.text.isNotEmpty && msg.id != '0000' && !msg.fromIntegration) {
        _aiResponse = msg.text;
        onboardingProvider.onVoiceResponseReceived(msg.text);
        setState(() => _showContinue = true);
        return;
      }
    }
  }

  @override
  void dispose() {
    _pulseController.dispose();
    _messageProvider.removeListener(_onMessagesChanged);
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
    if (_aiResponse != null) {
      return Column(
        children: [
          const Icon(Icons.check_circle, color: Color(0xFF4CAF50), size: 48),
          const SizedBox(height: 16),
          if (_userQuestion != null && _userQuestion!.isNotEmpty) ...[
            Container(
              padding: const EdgeInsets.all(16),
              decoration: BoxDecoration(
                color: Colors.white.withValues(alpha: 0.05),
                borderRadius: BorderRadius.circular(12),
              ),
              child: Row(
                crossAxisAlignment: CrossAxisAlignment.start,
                children: [
                  const Icon(Icons.person, color: Color(0xFF9E9E9E), size: 18),
                  const SizedBox(width: 8),
                  Expanded(
                    child: Text(
                      _userQuestion!,
                      style: const TextStyle(color: Color(0xFF9E9E9E), fontSize: 14, height: 1.3),
                      maxLines: 3,
                      overflow: TextOverflow.ellipsis,
                    ),
                  ),
                ],
              ),
            ),
            const SizedBox(height: 12),
          ],
          Container(
            padding: const EdgeInsets.all(16),
            decoration: BoxDecoration(
              color: Colors.white.withValues(alpha: 0.08),
              borderRadius: BorderRadius.circular(12),
            ),
            child: Row(
              crossAxisAlignment: CrossAxisAlignment.start,
              children: [
                const Icon(Icons.smart_toy, color: Colors.white, size: 18),
                const SizedBox(width: 8),
                Expanded(
                  child: Text(
                    _stripMarkdown(_aiResponse!),
                    style: const TextStyle(color: Colors.white, fontSize: 15, height: 1.4),
                    maxLines: 8,
                    overflow: TextOverflow.ellipsis,
                  ),
                ),
              ],
            ),
          ),
        ],
      );
    }

    if (provider.questionSent) {
      return Column(
        children: [
          const SizedBox(width: 48, height: 48, child: CircularProgressIndicator(color: Colors.white, strokeWidth: 3)),
          const SizedBox(height: 16),
          const Text('Processing...', style: TextStyle(color: Colors.white, fontSize: 18)),
          if (_userQuestion != null && _userQuestion!.isNotEmpty) ...[
            const SizedBox(height: 16),
            Text(
              '"$_userQuestion"',
              style: const TextStyle(color: Color(0xFF9E9E9E), fontSize: 14, fontStyle: FontStyle.italic),
              textAlign: TextAlign.center,
              maxLines: 2,
              overflow: TextOverflow.ellipsis,
            ),
          ],
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
