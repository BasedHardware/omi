import 'package:flutter/gestures.dart';
import 'package:flutter/material.dart';

import 'package:provider/provider.dart';

import 'package:omi/providers/auth_provider.dart';
import 'package:omi/utils/l10n_extensions.dart';

class AiConsentWidget extends StatefulWidget {
  final VoidCallback onAgree;

  const AiConsentWidget({super.key, required this.onAgree});

  @override
  State<AiConsentWidget> createState() => _AiConsentWidgetState();
}

class _AiConsentWidgetState extends State<AiConsentWidget> {
  final TapGestureRecognizer _privacyRecognizer = TapGestureRecognizer();
  final TapGestureRecognizer _termsRecognizer = TapGestureRecognizer();

  @override
  void initState() {
    super.initState();
    final provider = context.read<AuthenticationProvider>();
    _privacyRecognizer.onTap = provider.openPrivacyPolicy;
    _termsRecognizer.onTap = provider.openTermsOfService;
  }

  @override
  void dispose() {
    _privacyRecognizer.dispose();
    _termsRecognizer.dispose();
    super.dispose();
  }

  @override
  Widget build(BuildContext context) {
    return Column(
      children: [
        Expanded(child: Container()),
        Container(
          width: double.infinity,
          padding: EdgeInsets.fromLTRB(32, 26, 32, MediaQuery.of(context).padding.bottom + 8),
          decoration: const BoxDecoration(
            color: Colors.black,
            borderRadius: BorderRadius.only(topLeft: Radius.circular(40), topRight: Radius.circular(40)),
          ),
          child: SafeArea(
            top: false,
            child: Column(
              mainAxisSize: MainAxisSize.min,
              crossAxisAlignment: CrossAxisAlignment.start,
              children: [
                Text(
                  context.l10n.dataAndPrivacy,
                  style: const TextStyle(
                    color: Colors.white,
                    fontSize: 28,
                    fontWeight: FontWeight.bold,
                    height: 1.2,
                    fontFamily: 'Manrope',
                  ),
                ),
                const SizedBox(height: 16),
                Text(
                  context.l10n.consentDataMessage,
                  style: const TextStyle(color: Colors.white, fontSize: 15, height: 1.5, fontFamily: 'Manrope'),
                ),
                const SizedBox(height: 16),
                RichText(
                  text: TextSpan(
                    style: TextStyle(
                      color: Colors.white.withValues(alpha: 0.7),
                      fontSize: 13,
                      height: 1.4,
                      fontFamily: 'Manrope',
                    ),
                    children: [
                      TextSpan(text: context.l10n.yourDataIsProtected),
                      TextSpan(
                        text: context.l10n.privacyPolicy,
                        style: const TextStyle(color: Colors.white, decoration: TextDecoration.underline),
                        recognizer: _privacyRecognizer,
                      ),
                      TextSpan(text: context.l10n.and),
                      TextSpan(
                        text: context.l10n.termsOfService,
                        style: const TextStyle(color: Colors.white, decoration: TextDecoration.underline),
                        recognizer: _termsRecognizer,
                      ),
                      const TextSpan(text: '.'),
                    ],
                  ),
                ),
                const SizedBox(height: 28),
                SizedBox(
                  width: double.infinity,
                  height: 56,
                  child: ElevatedButton(
                    onPressed: widget.onAgree,
                    style: ElevatedButton.styleFrom(
                      backgroundColor: Colors.white,
                      foregroundColor: Colors.black,
                      shape: RoundedRectangleBorder(borderRadius: BorderRadius.circular(28)),
                      elevation: 0,
                    ),
                    child: Text(
                      context.l10n.agreeAndContinue,
                      style: const TextStyle(fontSize: 18, fontWeight: FontWeight.w600, fontFamily: 'Manrope'),
                    ),
                  ),
                ),
              ],
            ),
          ),
        ),
      ],
    );
  }
}
