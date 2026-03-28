import 'package:flutter/material.dart';

import 'package:provider/provider.dart';

import 'package:omi/backend/schema/message.dart';
import 'package:omi/providers/device_onboarding_provider.dart';
import 'package:omi/providers/message_provider.dart';
import 'package:omi/pages/onboarding/interactive_device_onboarding/widgets/onboarding_step_scaffold.dart';

String _stripMarkdown(String text) {
  return text
      .replaceAllMapped(RegExp(r'\*\*(.+?)\*\*'), (m) => m[1]!)
      .replaceAllMapped(RegExp(r'\*(.+?)\*'), (m) => m[1]!)
      .replaceAllMapped(RegExp(r'__(.+?)__'), (m) => m[1]!)
      .replaceAllMapped(RegExp(r'_(.+?)_'), (m) => m[1]!)
      .replaceAllMapped(RegExp(r'~~(.+?)~~'), (m) => m[1]!)
      .replaceAllMapped(RegExp(r'`(.+?)`'), (m) => m[1]!);
}

class SinglePressStep extends StatefulWidget {
  final VoidCallback onComplete;

  const SinglePressStep({super.key, required this.onComplete});

  @override
  State<SinglePressStep> createState() => _SinglePressStepState();
}

class _SinglePressStepState extends State<SinglePressStep> {
  late MessageProvider _messageProvider;
  bool _showContinue = false;

  late int _messageCountAtStart;
  String? _userQuestion;
  String? _aiResponse;

  @override
  void initState() {
    super.initState();
    _messageProvider = context.read<MessageProvider>();
    _messageCountAtStart = _messageProvider.messages.length;
    _messageProvider.addListener(_onMessagesChanged);
  }

  void _onMessagesChanged() {
    if (!mounted || _aiResponse != null) return;

    final onboardingProvider = context.read<DeviceOnboardingProvider>();
    if (!onboardingProvider.questionSent) return;

    if (_messageProvider.messages.length <= _messageCountAtStart) return;
    final newMessages = _messageProvider.messages.sublist(_messageCountAtStart);

    for (final msg in newMessages) {
      if (msg.sender == MessageSender.human && _userQuestion == null) {
        _userQuestion = msg.text;
      }
    }

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
    _messageProvider.removeListener(_onMessagesChanged);
    super.dispose();
  }

  @override
  Widget build(BuildContext context) {
    return Consumer<DeviceOnboardingProvider>(
      builder: (context, provider, _) {
        return OnboardingStepScaffold(
          title: 'Ask Omi a Question',
          subtitle: _aiResponse != null ? '' : 'Press the button once, speak your question, then press again when done',
          currentStep: 1,
          content: Column(
            children: [
              const Spacer(flex: 1),
              _buildContent(provider),
              const Spacer(flex: 2),
            ],
          ),
          bottomAction: _showContinue ? OnboardingContinueButton(onPressed: widget.onComplete) : null,
        );
      },
    );
  }

  Widget _buildContent(DeviceOnboardingProvider provider) {
    // Response received
    if (_aiResponse != null) {
      return Container(
        width: double.infinity,
        padding: const EdgeInsets.all(20),
        decoration: BoxDecoration(
          color: Colors.white,
          borderRadius: BorderRadius.circular(20),
        ),
        child: Column(
          crossAxisAlignment: CrossAxisAlignment.start,
          children: [
            if (_userQuestion != null && _userQuestion!.isNotEmpty) ...[
              Text(
                _userQuestion!,
                style: TextStyle(color: Colors.black.withValues(alpha: 0.5), fontSize: 14, height: 1.3),
                maxLines: 2,
                overflow: TextOverflow.ellipsis,
              ),
              const SizedBox(height: 12),
              Divider(height: 1, color: Colors.black.withValues(alpha: 0.08)),
              const SizedBox(height: 12),
            ],
            Text(
              _stripMarkdown(_aiResponse!),
              style: const TextStyle(color: Colors.black, fontSize: 16, height: 1.5),
              maxLines: 10,
              overflow: TextOverflow.ellipsis,
            ),
          ],
        ),
      );
    }

    // Processing
    if (provider.questionSent) {
      return Container(
        padding: const EdgeInsets.symmetric(horizontal: 24, vertical: 20),
        decoration: BoxDecoration(
          color: Colors.white.withValues(alpha: 0.06),
          borderRadius: BorderRadius.circular(20),
        ),
        child: Column(
          children: [
            const SizedBox(
              width: 32,
              height: 32,
              child: CircularProgressIndicator(color: Colors.white, strokeWidth: 2.5),
            ),
            const SizedBox(height: 14),
            const Text('Processing your question...', style: TextStyle(color: Colors.white, fontSize: 16)),
            if (_userQuestion != null && _userQuestion!.isNotEmpty) ...[
              const SizedBox(height: 10),
              Text(
                '"$_userQuestion"',
                style: const TextStyle(color: Color(0xFF9E9E9E), fontSize: 14, fontStyle: FontStyle.italic),
                textAlign: TextAlign.center,
                maxLines: 2,
                overflow: TextOverflow.ellipsis,
              ),
            ],
          ],
        ),
      );
    }

    // Listening
    if (provider.voiceSessionActive) {
      return Container(
        padding: const EdgeInsets.symmetric(horizontal: 24, vertical: 20),
        decoration: BoxDecoration(
          color: const Color(0xFF4CAF50).withValues(alpha: 0.1),
          borderRadius: BorderRadius.circular(20),
          border: Border.all(color: const Color(0xFF4CAF50).withValues(alpha: 0.3)),
        ),
        child: const Row(
          mainAxisAlignment: MainAxisAlignment.center,
          children: [
            Icon(Icons.mic, color: Color(0xFF4CAF50), size: 22),
            SizedBox(width: 12),
            Text('Listening...', style: TextStyle(color: Color(0xFF4CAF50), fontSize: 17, fontWeight: FontWeight.w500)),
          ],
        ),
      );
    }

    // Waiting for button press
    return Container(
      padding: const EdgeInsets.symmetric(horizontal: 24, vertical: 24),
      decoration: BoxDecoration(
        color: Colors.white.withValues(alpha: 0.06),
        borderRadius: BorderRadius.circular(20),
      ),
      child: Column(
        children: [
          Icon(Icons.touch_app, color: Colors.white.withValues(alpha: 0.7), size: 40),
          const SizedBox(height: 14),
          const Text(
            'Press the button on your Omi',
            style: TextStyle(color: Colors.white, fontSize: 16, fontWeight: FontWeight.w500),
            textAlign: TextAlign.center,
          ),
          const SizedBox(height: 6),
          Text(
            'Then speak your question',
            style: TextStyle(color: Colors.white.withValues(alpha: 0.5), fontSize: 13),
          ),
        ],
      ),
    );
  }
}
