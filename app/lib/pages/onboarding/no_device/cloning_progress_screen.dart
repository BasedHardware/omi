import 'dart:async';
import 'package:flutter/material.dart';
import 'package:friend_private/providers/no_device_onboarding_provider.dart';
import 'package:provider/provider.dart';

class CloningProgressScreen extends StatefulWidget {
  final VoidCallback onNext;

  const CloningProgressScreen({
    super.key,
    required this.onNext,
  });

  @override
  State<CloningProgressScreen> createState() => _CloningProgressScreenState();
}

class _CloningProgressScreenState extends State<CloningProgressScreen> {
  int _currentStateIndex = 0;
  bool _isComplete = false;
  late Timer _timer;

  final List<_CloningState> _states = [
    _CloningState(
      title: 'Your account is connected',
      subtitle: '',
      showCheck: true,
      loadingText: 'Setting up\nyour Omi clone...',
    ),
    _CloningState(
      title: 'Favorite Words',
      messages: [
        'whatsup bro',
        'what did you learn this week?',
        'Avi sucks',
      ],
      loadingText: 'Training your clone\nto sound like you...',
    ),
    _CloningState(
      title: '',
      stats: [
        _StatItem('892', 'Unanswered texts'),
        _StatItem('4', 'Girls in your DMs'),
        _StatItem('3,485', 'Tags'),
        _StatItem('10', 'Missed\nopportunities'),
      ],
      loadingText: 'Summarizing\nyour DMs',
    ),
    _CloningState(
      title: '@pmar',
      subtitle: 'ca\n1.9M\nfollowers',
      description: 'You ghosted them...',
      loadingText: 'Summarizing\nyour DMs',
    ),
    _CloningState(
      title: '89',
      subtitle: 'Unanswered texts',
      loadingText: 'Responding\nto DMs',
    ),
    _CloningState(
      title: '0',
      subtitle: 'Unanswered texts',
      showCheck: true,
      loadingText: 'Responding\nto DMs',
    ),
  ];

  @override
  void initState() {
    super.initState();
    _startTimer();
  }

  void _startTimer() {
    const totalDuration = 30; // 30 seconds total
    final intervalDuration = totalDuration ~/ _states.length;
    
    _timer = Timer.periodic(Duration(seconds: intervalDuration), (timer) {
      if (_currentStateIndex < _states.length - 1) {
        setState(() {
          _currentStateIndex++;
        });
      } else {
        timer.cancel();
        setState(() {
          _isComplete = true;
        });
        widget.onNext();
      }
    });
  }

  @override
  void dispose() {
    _timer.cancel();
    super.dispose();
  }

  @override
  Widget build(BuildContext context) {
    final currentState = _states[_currentStateIndex];

    return Stack(
      children: [
        // Background image
        Positioned.fill(
          child: Image.asset(
            'assets/images/new_background.png',
            fit: BoxFit.cover,
          ),
        ),
        Scaffold(
          backgroundColor: Colors.transparent,
          body: SafeArea(
            child: Padding(
              padding: const EdgeInsets.symmetric(horizontal: 24.0),
              child: Column(
                children: [
                  const SizedBox(height: 48),
                  // Profile section
                  Consumer<NoDeviceOnboardingProvider>(
                    builder: (context, provider, child) {
                      return Column(
                        children: [
                          Container(
                            width: 80,
                            height: 80,
                            decoration: BoxDecoration(
                              shape: BoxShape.circle,
                              border: Border.all(
                                color: Colors.white.withOpacity(0.2),
                                width: 2,
                              ),
                            ),
                            child: ClipOval(
                              child: Image.network(
                                'https://unavatar.io/twitter/${provider.twitterHandle}',
                                fit: BoxFit.cover,
                                errorBuilder: (context, error, stackTrace) {
                                  return Container(
                                    color: Colors.grey[900],
                                    child: Icon(
                                      Icons.person,
                                      size: 40,
                                      color: Colors.white.withOpacity(0.5),
                                    ),
                                  );
                                },
                              ),
                            ),
                          ),
                          const SizedBox(height: 12),
                          Row(
                            mainAxisAlignment: MainAxisAlignment.center,
                            children: [
                              Text(
                                provider.fullName,
                                style: const TextStyle(
                                  color: Colors.white,
                                  fontSize: 20,
                                  fontWeight: FontWeight.bold,
                                ),
                              ),
                              const SizedBox(width: 4),
                              const Icon(
                                Icons.verified,
                                color: Colors.blue,
                                size: 20,
                              ),
                            ],
                          ),
                        ],
                      );
                    },
                  ),
                  const Spacer(),
                  // Content section
                  if (currentState.title.isNotEmpty) ...[
                    Text(
                      currentState.title,
                      style: Theme.of(context).textTheme.headlineMedium?.copyWith(
                            color: Colors.white,
                            fontWeight: FontWeight.bold,
                          ),
                      textAlign: TextAlign.center,
                    ),
                  ],
                  if (currentState.subtitle.isNotEmpty) ...[
                    const SizedBox(height: 4),
                    Text(
                      currentState.subtitle,
                      style: Theme.of(context).textTheme.titleMedium?.copyWith(
                            color: Colors.white,
                          ),
                      textAlign: TextAlign.center,
                    ),
                  ],
                  if (currentState.description != null) ...[
                    const SizedBox(height: 8),
                    Text(
                      currentState.description!,
                      style: TextStyle(
                        color: Colors.white.withOpacity(0.7),
                        fontSize: 16,
                      ),
                      textAlign: TextAlign.center,
                    ),
                  ],
                  if (currentState.messages != null) ...[
                    const SizedBox(height: 24),
                    ...currentState.messages!.map((message) => Container(
                          margin: const EdgeInsets.only(bottom: 12),
                          padding: const EdgeInsets.symmetric(horizontal: 20, vertical: 12),
                          decoration: BoxDecoration(
                            color: Colors.blue,
                            borderRadius: BorderRadius.circular(20),
                          ),
                          child: Text(
                            message,
                            style: const TextStyle(
                              color: Colors.white,
                              fontSize: 16,
                            ),
                          ),
                        )),
                  ],
                  if (currentState.stats != null) ...[
                    const SizedBox(height: 24),
                    ...currentState.stats!.map((stat) => Padding(
                          padding: const EdgeInsets.only(bottom: 16),
                          child: Column(
                            children: [
                              Text(
                                stat.value,
                                style: const TextStyle(
                                  color: Colors.white,
                                  fontSize: 32,
                                  fontWeight: FontWeight.bold,
                                ),
                              ),
                              const SizedBox(height: 4),
                              Text(
                                stat.label,
                                style: TextStyle(
                                  color: Colors.white.withOpacity(0.7),
                                  fontSize: 16,
                                ),
                                textAlign: TextAlign.center,
                              ),
                            ],
                          ),
                        )),
                  ],
                  if (currentState.showCheck ?? false) ...[
                    const SizedBox(height: 24),
                    Container(
                      width: 48,
                      height: 48,
                      decoration: const BoxDecoration(
                        color: Colors.green,
                        shape: BoxShape.circle,
                      ),
                      child: const Icon(
                        Icons.check,
                        color: Colors.white,
                        size: 32,
                      ),
                    ),
                  ],
                  const Spacer(),
                  // Loading section
                  Column(
                    children: [
                      const CircularProgressIndicator(
                        valueColor: AlwaysStoppedAnimation<Color>(Colors.white),
                      ),
                      const SizedBox(height: 24),
                      Text(
                        currentState.loadingText,
                        style: TextStyle(
                          color: Colors.white.withOpacity(0.8),
                          fontSize: 16,
                        ),
                        textAlign: TextAlign.center,
                      ),
                    ],
                  ),
                  const SizedBox(height: 48),
                ],
              ),
            ),
          ),
        ),
      ],
    );
  }
}

class _CloningState {
  final String title;
  final String subtitle;
  final String? description;
  final List<String>? messages;
  final List<_StatItem>? stats;
  final bool? showCheck;
  final String loadingText;

  _CloningState({
    required this.title,
    this.subtitle = '',
    this.description,
    this.messages,
    this.stats,
    this.showCheck,
    required this.loadingText,
  });
}

class _StatItem {
  final String value;
  final String label;

  _StatItem(this.value, this.label);
} 