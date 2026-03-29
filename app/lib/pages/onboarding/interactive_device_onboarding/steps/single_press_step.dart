import 'dart:math';

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

class _SinglePressStepState extends State<SinglePressStep> with SingleTickerProviderStateMixin {
  late AnimationController _waveController;
  late MessageProvider _messageProvider;
  bool _showContinue = false;

  late int _messageCountAtStart;
  String? _userQuestion;
  String? _aiResponse;

  @override
  void initState() {
    super.initState();
    _waveController = AnimationController(vsync: this, duration: const Duration(seconds: 3))..repeat();
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
    _waveController.dispose();
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
        padding: const EdgeInsets.symmetric(horizontal: 24, vertical: 24),
        decoration: BoxDecoration(
          color: Colors.white.withValues(alpha: 0.06),
          borderRadius: BorderRadius.circular(20),
        ),
        child: Column(
          children: [
            AnimatedBuilder(
              animation: _waveController,
              builder: (context, _) {
                return ShaderMask(
                  shaderCallback: (bounds) {
                    return LinearGradient(
                      colors: [
                        Colors.white.withValues(alpha: 0.3),
                        Colors.white,
                        Colors.white.withValues(alpha: 0.3),
                      ],
                      stops: [
                        (_waveController.value - 0.3).clamp(0.0, 1.0),
                        _waveController.value,
                        (_waveController.value + 0.3).clamp(0.0, 1.0),
                      ],
                      begin: Alignment.centerLeft,
                      end: Alignment.centerRight,
                    ).createShader(bounds);
                  },
                  child: const Text(
                    'Processing your question...',
                    style: TextStyle(color: Colors.white, fontSize: 17, fontWeight: FontWeight.w500),
                  ),
                );
              },
            ),
            if (_userQuestion != null && _userQuestion!.isNotEmpty) ...[
              const SizedBox(height: 12),
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
      return AnimatedBuilder(
        animation: _waveController,
        builder: (context, _) {
          return Container(
            padding: const EdgeInsets.symmetric(horizontal: 24, vertical: 20),
            decoration: BoxDecoration(
              color: const Color(0xFF4CAF50).withValues(alpha: 0.1),
              borderRadius: BorderRadius.circular(20),
              border: Border.all(color: const Color(0xFF4CAF50).withValues(alpha: 0.3)),
            ),
            child: Row(
              children: [
                const Icon(Icons.mic, color: Color(0xFF4CAF50), size: 22),
                const SizedBox(width: 14),
                Expanded(
                  child: CustomPaint(
                    painter: _StaticWaveformPainter(
                      phase: _waveController.value * 2 * pi * 3,
                      color: const Color(0xFF4CAF50).withValues(alpha: 0.5),
                    ),
                    size: const Size(double.infinity, 28),
                  ),
                ),
                const SizedBox(width: 14),
                const Text('Listening...', style: TextStyle(color: Color(0xFF4CAF50), fontSize: 14, fontWeight: FontWeight.w500)),
              ],
            ),
          );
        },
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

class _StaticWaveformPainter extends CustomPainter {
  final double phase;
  final Color color;

  _StaticWaveformPainter({required this.phase, required this.color});

  @override
  void paint(Canvas canvas, Size size) {
    final paint = Paint()
      ..color = color
      ..strokeWidth = 2.0
      ..style = PaintingStyle.stroke
      ..strokeCap = StrokeCap.round;

    final path = Path();
    final midY = size.height / 2;
    for (double x = 0; x < size.width; x += 1) {
      final n = x / size.width;
      // Amplitude pulses in place instead of scrolling
      final ampMod = 0.6 + 0.4 * sin(phase);
      final y = midY + sin(n * 4 * pi) * 8 * ampMod + sin(n * 11 * pi) * 4 * ampMod;
      if (x == 0) {
        path.moveTo(x, y);
      } else {
        path.lineTo(x, y);
      }
    }
    canvas.drawPath(path, paint);
  }

  @override
  bool shouldRepaint(_StaticWaveformPainter oldDelegate) => phase != oldDelegate.phase;
}
