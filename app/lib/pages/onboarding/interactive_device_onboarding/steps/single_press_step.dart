import 'dart:math';

import 'package:flutter/material.dart';

import 'package:omi/ui/omi_tokens.dart';

import 'package:provider/provider.dart';

import 'package:omi/backend/schema/message.dart';
import 'package:omi/gen/assets.gen.dart';
import 'package:omi/mobile/native_ui/ios_native_surface.dart';
import 'package:omi/providers/device_onboarding_provider.dart';
import 'package:omi/providers/message_provider.dart';
import 'package:omi/pages/onboarding/interactive_device_onboarding/widgets/onboarding_step_scaffold.dart';
import 'package:omi/utils/l10n_extensions.dart';

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

class _SinglePressStepState extends State<SinglePressStep> with TickerProviderStateMixin {
  late AnimationController _animController;
  late AnimationController _bounceController;
  late MessageProvider _messageProvider;
  bool _showContinue = false;
  bool _wasListening = false;
  bool _bounceStopped = false;

  late int _messageCountAtStart;
  String? _userQuestion;
  String? _aiResponse;

  @override
  void initState() {
    super.initState();
    // Both run only while the classic step is mounted ([DeviceTutorialClassicAnimations]).
    _animController = AnimationController(vsync: this, duration: const Duration(seconds: 4));
    _bounceController = AnimationController(vsync: this, duration: const Duration(milliseconds: 1200));
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
    _animController.dispose();
    _bounceController.dispose();
    _messageProvider.removeListener(_onMessagesChanged);
    super.dispose();
  }

  void _startClassicAnimations() {
    _animController.repeat();
    // The bounce stops for good once listening starts.
    if (!_bounceStopped) _bounceController.repeat();
  }

  void _stopClassicAnimations() {
    _animController.stop();
    _bounceController.stop();
  }

  @override
  Widget build(BuildContext context) {
    return Consumer<DeviceOnboardingProvider>(
      builder: (context, provider, _) {
        if (provider.voiceSessionActive && !_wasListening) {
          _wasListening = true;
          _bounceStopped = true;
          _bounceController.stop();
        } else if (!provider.voiceSessionActive && _wasListening) {
          _wasListening = false;
        }

        final classic = DeviceTutorialClassicAnimations(
            onMount: _startClassicAnimations,
            onUnmount: _stopClassicAnimations,
            child: OnboardingStepScaffold(
              title: context.l10n.deviceOnboardingAskQuestionTitle,
              subtitle: _aiResponse != null ? '' : context.l10n.deviceOnboardingAskQuestionSubtitle,
              content: Column(children: [const Spacer(flex: 1), _buildContent(provider), const Spacer(flex: 2)]),
              bottomAction: _showContinue ? OnboardingContinueButton(onPressed: widget.onComplete) : null,
            ));
        if (!deviceTutorialNative(context)) return classic;
        return _nativeSurface(provider, classic);
      },
    );
  }

  /// The bounce, pulse and shimmer are decorative; SF Symbols and the same copy replace them natively.
  /// The question and answer stay literal text: the answer is shown markdown-stripped, as classic does.
  Widget _nativeSurface(DeviceOnboardingProvider provider, Widget classic) {
    final l10n = context.l10n;
    final question = _userQuestion;
    final answer = _aiResponse;
    return IosNativeSurface(title: l10n.deviceOnboardingAskQuestionTitle, fallback: classic, sections: [
      NativeSection('dev_tut_press', [
        if (answer == null)
          if (provider.questionSent)
            NativeRow('dev_tut_press_state', l10n.deviceOnboardingProcessingQuestion,
                kind: 'label', symbol: 'ellipsis.bubble', subtitle: l10n.deviceOnboardingAskQuestionSubtitle)
          else if (provider.voiceSessionActive)
            NativeRow('dev_tut_press_state', l10n.deviceOnboardingListening,
                kind: 'label', symbol: 'waveform', subtitle: l10n.deviceOnboardingAskQuestionSubtitle)
          else
            NativeRow('dev_tut_press_state', l10n.deviceOnboardingAskQuestionSubtitle,
                kind: 'label', symbol: 'hand.tap'),
        if (question != null && question.isNotEmpty && (answer != null || provider.questionSent))
          NativeRow('dev_tut_question', deviceTutorialNativeText(question), kind: 'message_user', plainText: true),
        if (answer != null)
          NativeRow('dev_tut_answer', deviceTutorialNativeText(_stripMarkdown(answer)),
              kind: 'message_ai', plainText: true),
      ]),
      if (_showContinue) NativeSection('dev_tut_actions', [deviceTutorialContinueRow(context, widget.onComplete)]),
    ]);
  }

  Widget _buildContent(DeviceOnboardingProvider provider) {
    // Response received
    if (_aiResponse != null) {
      return Container(
        width: double.infinity,
        padding: const EdgeInsets.all(20),
        decoration: BoxDecoration(color: OmiColors.surface1, borderRadius: BorderRadius.circular(20)),
        child: Column(
          crossAxisAlignment: CrossAxisAlignment.start,
          children: [
            if (_userQuestion != null && _userQuestion!.isNotEmpty) ...[
              Text(
                _userQuestion!,
                style: TextStyle(color: OmiColors.textSecondary, fontSize: 14, height: 1.3),
                maxLines: 2,
                overflow: TextOverflow.ellipsis,
              ),
              const SizedBox(height: 12),
              Divider(height: 1, color: OmiColors.border),
              const SizedBox(height: 12),
            ],
            Text(
              _stripMarkdown(_aiResponse!),
              style: TextStyle(color: OmiColors.textPrimary, fontSize: 16, height: 1.5),
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
        decoration: BoxDecoration(color: OmiColors.surface1, borderRadius: BorderRadius.circular(20)),
        child: Column(
          children: [
            AnimatedBuilder(
              animation: _animController,
              builder: (context, _) {
                return ShaderMask(
                  shaderCallback: (bounds) {
                    return LinearGradient(
                      colors: [
                        OmiColors.textPrimary.withValues(alpha: 0.3),
                        OmiColors.textPrimary,
                        OmiColors.textPrimary.withValues(alpha: 0.3),
                      ],
                      stops: [
                        (_animController.value - 0.3).clamp(0.0, 1.0),
                        _animController.value,
                        (_animController.value + 0.3).clamp(0.0, 1.0),
                      ],
                      begin: Alignment.centerLeft,
                      end: Alignment.centerRight,
                    ).createShader(bounds);
                  },
                  child: Text(
                    context.l10n.deviceOnboardingProcessingQuestion,
                    style: TextStyle(color: OmiColors.textPrimary, fontSize: 17, fontWeight: FontWeight.w500),
                  ),
                );
              },
            ),
            if (_userQuestion != null && _userQuestion!.isNotEmpty) ...[
              const SizedBox(height: 12),
              Text(
                '"$_userQuestion"',
                style: TextStyle(color: OmiColors.textSecondary, fontSize: 14, fontStyle: FontStyle.italic),
                textAlign: TextAlign.center,
                maxLines: 2,
                overflow: TextOverflow.ellipsis,
              ),
            ],
          ],
        ),
      );
    }

    // Listening — Omi with pulsating circles + waveform
    if (provider.voiceSessionActive) {
      return Column(
        children: [
          _buildOmiWithPulse(),
          const SizedBox(height: 24),
          AnimatedBuilder(
            animation: _animController,
            builder: (context, _) {
              return Container(
                padding: const EdgeInsets.symmetric(horizontal: 24, vertical: 16),
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
                          phase: _animController.value * 2 * pi * 3,
                          color: const Color(0xFF4CAF50).withValues(alpha: 0.5),
                        ),
                        size: const Size(double.infinity, 28),
                      ),
                    ),
                    const SizedBox(width: 14),
                    Text(
                      context.l10n.deviceOnboardingListening,
                      style: const TextStyle(color: Color(0xFF4CAF50), fontSize: 14, fontWeight: FontWeight.w500),
                    ),
                  ],
                ),
              );
            },
          ),
        ],
      );
    }

    // Waiting — Omi with bounce click animation
    return _buildOmiWithBounce();
  }

  Widget _buildOmiWithPulse() {
    final pixelRatio = MediaQuery.of(context).devicePixelRatio;
    const imageSize = 140.0;
    const containerSize = imageSize + 120.0;

    return AnimatedBuilder(
      animation: _animController,
      builder: (context, child) {
        return SizedBox(
          width: containerSize,
          height: containerSize,
          child: Stack(
            alignment: Alignment.center,
            children: [
              for (int i = 0; i < 3; i++) _buildPulseCircle(i, imageSize, containerSize),
              Image.asset(
                Assets.images.omiWithoutRope.path,
                height: imageSize,
                width: imageSize,
                cacheHeight: (imageSize * pixelRatio).round(),
                cacheWidth: (imageSize * pixelRatio).round(),
              ),
            ],
          ),
        );
      },
    );
  }

  Widget _buildPulseCircle(int index, double imageSize, double containerSize) {
    final progress = (_animController.value + index * 0.33) % 1.0;
    final diameter = imageSize + (containerSize - imageSize) * progress;
    final opacity = (1.0 - progress).clamp(0.0, 0.25);

    return Container(
      width: diameter,
      height: diameter,
      decoration: BoxDecoration(
        shape: BoxShape.circle,
        border: Border.all(color: OmiColors.textPrimary.withValues(alpha: opacity), width: 1.5),
      ),
    );
  }

  Widget _buildOmiWithBounce() {
    final pixelRatio = MediaQuery.of(context).devicePixelRatio;
    const imageSize = 140.0;

    return AnimatedBuilder(
      animation: _bounceController,
      builder: (context, _) {
        final t = _bounceController.value;
        // 0.0-0.3: scale down, 0.3-0.5: bounce back, 0.5-1.0: rest
        double scale;
        if (t < 0.3) {
          scale = 1.0 - 0.1 * (t / 0.3);
        } else if (t < 0.5) {
          scale = 0.9 + 0.1 * ((t - 0.3) / 0.2);
        } else {
          scale = 1.0;
        }

        return Transform.scale(
          scale: scale,
          child: Image.asset(
            Assets.images.omiWithoutRope.path,
            height: imageSize,
            width: imageSize,
            cacheHeight: (imageSize * pixelRatio).round(),
            cacheWidth: (imageSize * pixelRatio).round(),
          ),
        );
      },
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
