import 'dart:async';

import 'package:flutter/material.dart';
import 'package:flutter_provider_utilities/flutter_provider_utilities.dart';
import 'package:provider/provider.dart';

import 'package:omi/backend/preferences.dart';
import 'package:omi/pages/settings/language_selection_dialog.dart';
import 'package:omi/providers/capture_provider.dart';
import 'package:omi/providers/home_provider.dart';
import 'package:omi/providers/speech_profile_provider.dart';
import 'package:omi/utils/l10n_extensions.dart';
import 'package:omi/utils/logger.dart';
import 'package:omi/widgets/dialog.dart';

class SpeechProfileWidget extends StatefulWidget {
  final VoidCallback goNext;
  final VoidCallback onSkip;

  const SpeechProfileWidget({super.key, required this.goNext, required this.onSkip});

  @override
  State<SpeechProfileWidget> createState() => _SpeechProfileWidgetState();
}

class _SpeechProfileWidgetState extends State<SpeechProfileWidget> {
  final ScrollController _scrollController = ScrollController();
  final List<_ChatMessage> _messages = [];

  int _lastQuestionIndex = -1;
  int _textLengthAtQuestionStart = 0;

  SpeechProfileProvider? _speechProvider;

  @override
  void initState() {
    super.initState();

    WidgetsBinding.instance.addPostFrameCallback((_) async {
      if (!mounted) return;
      if (!context.read<HomeProvider>().hasSetPrimaryLanguage) {
        await LanguageSelectionDialog.show(context);
      }
    });
    SharedPreferencesUtil().onboardingCompleted = true;
  }

  @override
  void didChangeDependencies() {
    super.didChangeDependencies();
    _speechProvider = context.read<SpeechProfileProvider>();
  }

  @override
  void dispose() {
    _speechProvider?.forceCompletionTimer?.cancel();
    _speechProvider?.forceCompletionTimer = null;
    _speechProvider?.close();

    _scrollController.dispose();
    super.dispose();
  }

  void _scrollToBottom() {
    WidgetsBinding.instance.addPostFrameCallback((_) {
      if (_scrollController.hasClients) {
        _scrollController.animateTo(
          _scrollController.position.maxScrollExtent,
          duration: const Duration(milliseconds: 300),
          curve: Curves.easeOut,
        );
      }
    });
  }

  void _onQuestionChanged(SpeechProfileProvider provider) {
    if (provider.currentQuestionIndex != _lastQuestionIndex && provider.currentQuestion.isNotEmpty) {
      // Save the previous response if we have one (only the NEW portion since last question)
      if (_lastQuestionIndex >= 0) {
        final fullText = provider.text.trim();
        final newResponse =
            fullText.length > _textLengthAtQuestionStart ? fullText.substring(_textLengthAtQuestionStart).trim() : '';
        if (newResponse.isNotEmpty) {
          _messages.add(_ChatMessage(text: newResponse, isOmi: false));
        }
      }

      // Add the new question
      _messages.add(_ChatMessage(text: provider.currentQuestion, isOmi: true));
      _lastQuestionIndex = provider.currentQuestionIndex;
      _textLengthAtQuestionStart = provider.text.trim().length;

      _scrollToBottom();
    }
  }

  String _getLoadingText(SpeechProfileLoadingState state) {
    switch (state) {
      case SpeechProfileLoadingState.uploading:
        return context.l10n.uploadingVoiceProfile;
      case SpeechProfileLoadingState.memorizing:
        return context.l10n.memorizingYourVoice;
      case SpeechProfileLoadingState.personalizing:
        return context.l10n.personalizingExperience;
      case SpeechProfileLoadingState.allSet:
        return context.l10n.youreAllSet;
    }
  }

  Future<void> _restartDeviceRecording() async {
    Logger.debug("restartDeviceRecording $mounted");
    if (mounted) {
      Provider.of<CaptureProvider>(context, listen: false).clearTranscripts();
      final device = Provider.of<SpeechProfileProvider>(context, listen: false).deviceProvider?.connectedDevice;
      if (device != null) {
        Provider.of<CaptureProvider>(context, listen: false).streamDeviceRecording(device: device);
      }
    }
  }

  Future<void> _stopAllRecording() async {
    Logger.debug("stopAllRecording $mounted");
    if (mounted) {
      await Provider.of<CaptureProvider>(context, listen: false).stopStreamDeviceRecording();
    }
  }

  void _resetChatState() {
    _messages.clear();
    _lastQuestionIndex = -1;
    _textLengthAtQuestionStart = 0;
  }

  Future<void> _handleStart(SpeechProfileProvider provider) async {
    if (!context.read<HomeProvider>().hasSetPrimaryLanguage) {
      await LanguageSelectionDialog.show(context);
    }

    // Clear previous chat history when starting fresh
    _resetChatState();

    await _stopAllRecording();

    bool success = await provider.initialise(
      usePhoneMic: true,
      processConversationCallback: () {
        Provider.of<CaptureProvider>(context, listen: false).forceProcessingCurrentConversation();
      },
    );

    if (!success) return;

    provider.forceCompletionTimer = Timer(Duration(seconds: provider.maxDuration), () {
      provider.finalize();
    });
  }

  void _showErrorDialog(String error, SpeechProfileProvider provider) {
    String title = '';
    String desc = '';
    String buttonText = context.l10n.ok;
    VoidCallback onPressed = () => Navigator.pop(context);

    switch (error) {
      case 'SOCKET_INIT_FAILED':
        title = context.l10n.connectionError;
        desc = context.l10n.connectionErrorDesc;
        break;
      case 'MULTIPLE_SPEAKERS':
        title = context.l10n.invalidRecordingMultipleSpeakers;
        desc = context.l10n.multipleSpeakersDesc;
        buttonText = context.l10n.tryAgain;
        onPressed = () {
          provider.close();
          Navigator.pop(context);
        };
        break;
      case 'TOO_SHORT':
        title = context.l10n.invalidRecordingMultipleSpeakers;
        desc = context.l10n.tooShortDesc;
        break;
      case 'INVALID_RECORDING':
        title = context.l10n.invalidRecordingMultipleSpeakers;
        desc = context.l10n.invalidRecordingDesc;
        break;
      case 'NO_SPEECH':
        title = context.l10n.areYouThere;
        desc = context.l10n.noSpeechDesc;
        break;
      case 'SOCKET_DISCONNECTED':
      case 'SOCKET_ERROR':
        title = context.l10n.connectionLost;
        desc = context.l10n.connectionLostDesc;
        buttonText = context.l10n.tryAgain;
        onPressed = () {
          provider.close();
          Navigator.pop(context);
        };
        break;
      default:
        return;
    }

    showDialog(
      context: context,
      barrierDismissible: false,
      builder: (c) => getDialog(context, onPressed, () {}, title, desc, okButtonText: buttonText, singleButton: true),
    );
  }

  @override
  Widget build(BuildContext context) {
    return PopScope(
      canPop: true,
      onPopInvokedWithResult: (didPop, result) async {
        context.read<SpeechProfileProvider>().close();
        _restartDeviceRecording();
      },
      child: Consumer2<SpeechProfileProvider, CaptureProvider>(
        builder: (context, provider, _, child) {
          // Track question changes
          if (provider.startedRecording && !provider.uploadingProfile && !provider.profileCompleted) {
            _onQuestionChanged(provider);
          }

          return MessageListener<SpeechProfileProvider>(
            showInfo: (info) {
              if (info == 'SCROLL_DOWN' || info == 'NEXT_QUESTION') {
                _scrollToBottom();
              }
            },
            showError: (error) => _showErrorDialog(error, provider),
            child: _buildBody(provider),
          );
        },
      ),
    );
  }

  Widget _buildBody(SpeechProfileProvider provider) {
    if (!provider.startedRecording) {
      return _buildWelcome(provider);
    } else if (provider.profileCompleted) {
      return _buildComplete();
    } else if (provider.uploadingProfile) {
      return _buildProcessing(provider);
    } else {
      return _buildConversation(provider);
    }
  }

  // ─────────────────────────────────────────────────────────────────────────
  // WELCOME STATE
  // ─────────────────────────────────────────────────────────────────────────
  Widget _buildWelcome(SpeechProfileProvider provider) {
    return Padding(
      padding: const EdgeInsets.symmetric(horizontal: 16),
      child: Column(
        mainAxisAlignment: MainAxisAlignment.center,
        children: [
          Text(
            context.l10n.speechProfileIntro,
            textAlign: TextAlign.center,
            style: const TextStyle(
              color: Colors.white,
              fontSize: 20,
              height: 1.4,
              fontWeight: FontWeight.w400,
            ),
          ),
          const SizedBox(height: 24),

          // Start button
          provider.isInitialising
              ? const CircularProgressIndicator(color: Colors.white)
              : MaterialButton(
                  onPressed: () => _handleStart(provider),
                  color: Colors.white,
                  padding: const EdgeInsets.symmetric(horizontal: 32, vertical: 14),
                  shape: RoundedRectangleBorder(borderRadius: BorderRadius.circular(28)),
                  child: Text(
                    context.l10n.getStarted,
                    style: const TextStyle(color: Colors.black),
                  ),
                ),

          const SizedBox(height: 16),

          // Skip button
          TextButton(
            onPressed: widget.onSkip,
            child: Text(
              context.l10n.skipForNow,
              style: TextStyle(color: Colors.grey.shade400, fontSize: 14),
            ),
          ),
        ],
      ),
    );
  }

  void _handleSkipQuestion(SpeechProfileProvider provider) {
    // Add a skipped message to show in the chat
    _messages.add(_ChatMessage(text: '[Skipped]', isOmi: false, isSkipped: true));
    _scrollToBottom();
    provider.skipCurrentQuestion();
  }

  // ─────────────────────────────────────────────────────────────────────────
  // CONVERSATION STATE
  // ─────────────────────────────────────────────────────────────────────────
  Widget _buildConversation(SpeechProfileProvider provider) {
    final fullText = provider.text.trim();
    // Only show the portion of text that's new since the current question started
    final currentResponse =
        fullText.length > _textLengthAtQuestionStart ? fullText.substring(_textLengthAtQuestionStart).trim() : '';
    final hasCurrentResponse = currentResponse.isNotEmpty;

    // Build list items: messages + current response (if any) + typing indicator (if waiting for next question)
    final List<Widget> chatItems = [];

    // Add all saved messages
    for (final msg in _messages) {
      chatItems.add(_buildMessageBubble(msg.text, msg.isOmi, isSkipped: msg.isSkipped));
    }

    // Add current response if user is speaking (this updates in real-time from provider.text)
    if (hasCurrentResponse) {
      chatItems.add(_buildMessageBubble(currentResponse, false));
      // Show typing indicator when user has responded (waiting for next question)
      chatItems.add(_buildOmiTypingIndicator());
    }

    return Column(
      children: [
        // Top bar with just progress
        Padding(
          padding: const EdgeInsets.fromLTRB(20, 12, 20, 8),
          child: Text(
            'Question ${provider.currentQuestionIndex + 1} of ${provider.totalQuestions > 0 ? provider.totalQuestions : 5}',
            style: TextStyle(
              color: Colors.grey.shade500,
              fontSize: 13,
              fontWeight: FontWeight.w500,
            ),
          ),
        ),

        // Chat area
        Expanded(
          child: ListView(
            controller: _scrollController,
            padding: const EdgeInsets.symmetric(horizontal: 16, vertical: 8),
            children: chatItems,
          ),
        ),

        // Bottom: visualizer + skip
        _buildBottomPanel(provider),
      ],
    );
  }

  Widget _buildBottomPanel(SpeechProfileProvider provider) {
    return Padding(
      padding: const EdgeInsets.fromLTRB(20, 20, 20, 32),
      child: Column(
        mainAxisSize: MainAxisSize.min,
        children: [
          _AudioWaveVisualizer(amplitude: provider.currentAmplitude),
          const SizedBox(height: 20),
          GestureDetector(
            onTap: () => _handleSkipQuestion(provider),
            child: Text(
              context.l10n.skipThisQuestion,
              style: TextStyle(
                color: Colors.grey.shade600,
                fontSize: 13,
              ),
            ),
          ),
        ],
      ),
    );
  }

  Widget _buildMessageBubble(String text, bool isOmi, {bool isSkipped = false}) {
    return Padding(
      padding: const EdgeInsets.only(bottom: 12),
      child: Row(
        mainAxisAlignment: isOmi ? MainAxisAlignment.start : MainAxisAlignment.end,
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          Flexible(
            child: Container(
              constraints: BoxConstraints(maxWidth: MediaQuery.of(context).size.width * 0.7),
              padding: const EdgeInsets.symmetric(horizontal: 14, vertical: 10),
              decoration: BoxDecoration(
                color: isSkipped
                    ? Colors.grey.shade800
                    : isOmi
                        ? Colors.grey.shade900
                        : Colors.white,
                borderRadius: BorderRadius.only(
                  topLeft: const Radius.circular(16),
                  topRight: const Radius.circular(16),
                  bottomLeft: Radius.circular(isOmi ? 4 : 16),
                  bottomRight: Radius.circular(isOmi ? 16 : 4),
                ),
              ),
              child: Text(
                text,
                style: TextStyle(
                  color: isSkipped
                      ? Colors.grey.shade500
                      : isOmi
                          ? Colors.white
                          : Colors.black,
                  fontSize: 15,
                  height: 1.3,
                  fontStyle: isSkipped ? FontStyle.italic : FontStyle.normal,
                ),
              ),
            ),
          ),
        ],
      ),
    );
  }

  Widget _buildOmiTypingIndicator() {
    return Padding(
      padding: const EdgeInsets.only(bottom: 12),
      child: Row(
        mainAxisAlignment: MainAxisAlignment.start,
        children: [
          Container(
            padding: const EdgeInsets.symmetric(horizontal: 14, vertical: 12),
            decoration: BoxDecoration(
              color: Colors.grey.shade900,
              borderRadius: const BorderRadius.only(
                topLeft: Radius.circular(16),
                topRight: Radius.circular(16),
                bottomLeft: Radius.circular(4),
                bottomRight: Radius.circular(16),
              ),
            ),
            child: _buildTypingDots(),
          ),
        ],
      ),
    );
  }

  Widget _buildTypingDots() {
    return Row(
      mainAxisSize: MainAxisSize.min,
      children: List.generate(3, (index) {
        return Padding(
          padding: EdgeInsets.only(right: index < 2 ? 4 : 0),
          child: _TypingDot(delay: index * 150),
        );
      }),
    );
  }

  // ─────────────────────────────────────────────────────────────────────────
  // PROCESSING STATE
  // ─────────────────────────────────────────────────────────────────────────
  Widget _buildProcessing(SpeechProfileProvider provider) {
    return Center(
      child: Column(
        mainAxisSize: MainAxisSize.min,
        children: [
          const CircularProgressIndicator(
            valueColor: AlwaysStoppedAnimation(Colors.white),
          ),
          const SizedBox(height: 20),
          Text(
            _getLoadingText(provider.loadingState),
            style: const TextStyle(color: Colors.white, fontSize: 16),
          ),
        ],
      ),
    );
  }

  // ─────────────────────────────────────────────────────────────────────────
  // COMPLETE STATE
  // ─────────────────────────────────────────────────────────────────────────
  Widget _buildComplete() {
    return Padding(
      padding: const EdgeInsets.symmetric(horizontal: 16),
      child: Column(
        mainAxisAlignment: MainAxisAlignment.center,
        children: [
          // Checkmark
          Container(
            width: 64,
            height: 64,
            decoration: const BoxDecoration(
              shape: BoxShape.circle,
              color: Colors.white,
            ),
            child: const Icon(Icons.check_rounded, color: Colors.black, size: 32),
          ),

          const SizedBox(height: 20),

          Text(
            context.l10n.youreAllSet,
            textAlign: TextAlign.center,
            style: const TextStyle(
              color: Colors.white,
              fontSize: 22,
              fontWeight: FontWeight.w600,
            ),
          ),

          const SizedBox(height: 8),

          Text(
            "I'll recognize your voice from now on.",
            textAlign: TextAlign.center,
            style: TextStyle(color: Colors.grey.shade400, fontSize: 15),
          ),

          const SizedBox(height: 24),

          // Continue button
          MaterialButton(
            onPressed: widget.goNext,
            color: Colors.white,
            padding: const EdgeInsets.symmetric(horizontal: 32, vertical: 14),
            shape: RoundedRectangleBorder(borderRadius: BorderRadius.circular(28)),
            child: Text(
              context.l10n.continueButton,
              style: const TextStyle(color: Colors.black),
            ),
          ),
        ],
      ),
    );
  }
}

class _ChatMessage {
  final String text;
  final bool isOmi;
  final bool isSkipped;
  _ChatMessage({required this.text, required this.isOmi, this.isSkipped = false});
}

class _AudioWaveVisualizer extends StatelessWidget {
  final double amplitude;
  static const int _barCount = 7;

  const _AudioWaveVisualizer({required this.amplitude});

  @override
  Widget build(BuildContext context) {
    return SizedBox(
      height: 40,
      child: Row(
        mainAxisAlignment: MainAxisAlignment.center,
        crossAxisAlignment: CrossAxisAlignment.end,
        children: List.generate(_barCount, (index) {
          // Middle bars are taller, edge bars shorter
          final distanceFromCenter = (index - _barCount ~/ 2).abs();
          final positionFactor = 1.0 - (distanceFromCenter * 0.12);

          // Slight variation per bar for organic feel
          final variation = ((index * 0.15) % 0.2) + 0.9;

          // Calculate bar height instantly (no animation delay)
          const baseHeight = 0.15;
          final amplitudeHeight = amplitude * positionFactor * variation;
          final totalHeight = (baseHeight + amplitudeHeight).clamp(0.1, 1.0);

          return Container(
            width: 4,
            height: 40 * totalHeight,
            margin: const EdgeInsets.symmetric(horizontal: 2),
            decoration: BoxDecoration(
              borderRadius: BorderRadius.circular(2),
              color: Colors.white.withValues(alpha: 0.5 + (totalHeight * 0.5)),
            ),
          );
        }),
      ),
    );
  }
}

class _TypingDot extends StatefulWidget {
  final int delay;
  const _TypingDot({required this.delay});

  @override
  State<_TypingDot> createState() => _TypingDotState();
}

class _TypingDotState extends State<_TypingDot> with SingleTickerProviderStateMixin {
  late AnimationController _controller;
  late Animation<double> _animation;

  @override
  void initState() {
    super.initState();
    _controller = AnimationController(
      duration: const Duration(milliseconds: 600),
      vsync: this,
    );
    _animation = Tween<double>(begin: 0.4, end: 1.0).animate(
      CurvedAnimation(parent: _controller, curve: Curves.easeInOut),
    );

    Future.delayed(Duration(milliseconds: widget.delay), () {
      if (mounted) {
        _controller.repeat(reverse: true);
      }
    });
  }

  @override
  void dispose() {
    _controller.dispose();
    super.dispose();
  }

  @override
  Widget build(BuildContext context) {
    return FadeTransition(
      opacity: _animation,
      child: Container(
        width: 6,
        height: 6,
        decoration: BoxDecoration(
          shape: BoxShape.circle,
          color: Colors.grey.shade400,
        ),
      ),
    );
  }
}
