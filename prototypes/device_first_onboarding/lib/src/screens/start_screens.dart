import 'package:flutter/material.dart';

import '../art.dart';
import '../theme.dart';
import '../widgets.dart';

/// 01 — Welcome.
class WelcomeScreen extends StatelessWidget {
  const WelcomeScreen({super.key, required this.onGetStarted});

  final VoidCallback onGetStarted;

  @override
  Widget build(BuildContext context) {
    final t = DfThemeScope.of(context);
    return DfPage(
      header: const DfHeroArt(height: 420),
      children: <Widget>[
        Text(
          'Omi',
          style: t.label(color: t.textTertiary, weight: FontWeight.w600),
        ),
        const DfHeadline('Your AI companion that remembers.', size: 34),
        const DfBody('Omi records your conversations and writes the summary and to-dos for you.'),
        const Spacer(),
        DfButton('Get Started', onPressed: onGetStarted),
      ],
    );
  }
}

/// 02 — Sign in. Stand-in for the existing `auth.dart` screen.
class SignInScreen extends StatelessWidget {
  const SignInScreen({super.key, required this.onContinue});

  final VoidCallback onContinue;

  @override
  Widget build(BuildContext context) {
    return DfPage(
      children: <Widget>[
        const Spacer(),
        const DfHeadline('Speak.\nTranscribe.\nSummarize.', size: 44),
        const Spacer(),
        DfButton('Continue with Apple', onPressed: onContinue),
        DfButton('Continue with Google', onPressed: onContinue, kind: DfButtonKind.secondary),
        const DfCaption('By continuing, you agree to our Privacy Policy and Terms of Use.'),
      ],
    );
  }
}

/// 03 — Data & Privacy. Copy from `ai_consent_widget.dart`.
class PrivacyScreen extends StatelessWidget {
  const PrivacyScreen({super.key, required this.onAgree, required this.onDifferentAccount});

  final VoidCallback onAgree;
  final VoidCallback onDifferentAccount;

  @override
  Widget build(BuildContext context) {
    final t = DfThemeScope.of(context);
    return DfPage(
      children: <Widget>[
        const DfHeadline('Data & Privacy'),
        DfCard(
          padding: const EdgeInsets.all(18),
          child: Column(
            crossAxisAlignment: CrossAxisAlignment.start,
            children: <Widget>[
              Text(
                'By continuing, your conversations, recordings, and personal information will be securely stored '
                'on our servers. Your audio and transcripts are processed by Deepgram (transcription) and OpenAI '
                "(analysis) to power Omi's features.",
                style: t.body(size: 15, height: 1.5),
              ),
              const SizedBox(height: 14),
              Text('Governed by our Privacy Policy and Terms of Service.', style: t.label(size: 14)),
            ],
          ),
        ),
        const Spacer(),
        DfButton('Agree & Continue', onPressed: onAgree),
        DfButton('Use a Different Account', onPressed: onDifferentAccount, kind: DfButtonKind.text),
      ],
    );
  }
}

/// 04 — The gate. Pairing is required, so the device question comes right
/// after sign-in, before the user spends time on setup they can't use.
class DeviceForkScreen extends StatelessWidget {
  const DeviceForkScreen({super.key, required this.onPair, required this.onOnTheWay, required this.onNoDevice});

  final VoidCallback onPair;
  final VoidCallback onOnTheWay;
  final VoidCallback onNoDevice;

  @override
  Widget build(BuildContext context) {
    return DfPage(
      children: <Widget>[
        const DfProductStage(height: 300),
        const DfHeadline('Do you have your Omi?'),
        const DfBody('The app works with the Omi pendant. Pair it now to finish setting up.'),
        const Spacer(),
        DfButton('Yes, pair my Omi', onPressed: onPair),
        DfButton("It's on the way", onPressed: onOnTheWay, kind: DfButtonKind.secondary),
        DfButton("I don't have one yet", onPressed: onNoDevice, kind: DfButtonKind.text),
      ],
    );
  }
}
