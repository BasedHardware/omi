import 'package:flutter/gestures.dart';
import 'package:flutter/material.dart';
import 'package:font_awesome_flutter/font_awesome_flutter.dart';
import 'package:omi/providers/auth_provider.dart';
import 'package:provider/provider.dart';

class ConsentBottomSheet extends StatelessWidget {
  final String authMethod; // 'google' or 'apple'
  final VoidCallback onContinue;

  const ConsentBottomSheet({
    super.key,
    required this.authMethod,
    required this.onContinue,
  });

  @override
  Widget build(BuildContext context) {
    return Container(
      decoration: const BoxDecoration(
        color: Color(0xFF1C1C1E),
        borderRadius: BorderRadius.vertical(top: Radius.circular(20)),
      ),
      child: Column(
        mainAxisSize: MainAxisSize.min,
        children: [
          // Handle bar
          Container(
            margin: const EdgeInsets.only(top: 12),
            width: 36,
            height: 4,
            decoration: BoxDecoration(
              color: Colors.white.withOpacity(0.3),
              borderRadius: BorderRadius.circular(2),
            ),
          ),

          Padding(
            padding: const EdgeInsets.all(24),
            child: Column(
              crossAxisAlignment: CrossAxisAlignment.start,
              children: [
                // Title
                const Text(
                  'Data & Privacy',
                  style: TextStyle(
                    color: Colors.white,
                    fontSize: 24,
                    fontWeight: FontWeight.bold,
                  ),
                ),

                const SizedBox(height: 16),

                // Icon and auth method
                Row(
                  children: [
                    Container(
                      padding: const EdgeInsets.all(8),
                      decoration: BoxDecoration(
                        color: authMethod == 'apple' ? Colors.white : const Color(0xFF4285F4),
                        borderRadius: BorderRadius.circular(8),
                      ),
                      child: Icon(
                        authMethod == 'apple' ? FontAwesomeIcons.apple : FontAwesomeIcons.google,
                        color: authMethod == 'apple' ? Colors.black : Colors.white,
                        size: 18,
                      ),
                    ),
                    const SizedBox(width: 12),
                    Text(
                      'Sign in with ${authMethod == 'apple' ? 'Apple' : 'Google'}',
                      style: const TextStyle(
                        color: Colors.white,
                        fontSize: 16,
                        fontWeight: FontWeight.w500,
                      ),
                    ),
                  ],
                ),

                const SizedBox(height: 20),

                // Main message
                const Text(
                  'By continuing, all data you share with this app (including your conversations, recordings, and personal information) will be securely stored on our servers to provide you with AI-powered insights and enable all app features.',
                  style: TextStyle(
                    color: Colors.white,
                    fontSize: 16,
                    height: 1.4,
                  ),
                ),

                const SizedBox(height: 16),

                // Privacy notice with clickable links
                RichText(
                  text: TextSpan(
                    style: const TextStyle(
                      color: Colors.white70,
                      fontSize: 14,
                      height: 1.4,
                    ),
                    children: [
                      const TextSpan(text: 'Your data is protected and governed by our '),
                      TextSpan(
                        text: 'Privacy Policy',
                        style: const TextStyle(
                          color: Colors.white,
                          decoration: TextDecoration.underline,
                        ),
                        recognizer: TapGestureRecognizer()
                          ..onTap = () {
                            context.read<AuthenticationProvider>().openPrivacyPolicy();
                          },
                      ),
                      const TextSpan(text: ' and '),
                      TextSpan(
                        text: 'Terms of Service',
                        style: const TextStyle(
                          color: Colors.white,
                          decoration: TextDecoration.underline,
                        ),
                        recognizer: TapGestureRecognizer()
                          ..onTap = () {
                            context.read<AuthenticationProvider>().openTermsOfService();
                          },
                      ),
                      const TextSpan(text: '.'),
                    ],
                  ),
                ),

                const SizedBox(height: 24),

                // Buttons
                Column(
                  children: [
                    // Continue button
                    SizedBox(
                      width: double.infinity,
                      height: 50,
                      child: ElevatedButton(
                        onPressed: () {
                          Navigator.of(context).pop();
                          onContinue();
                        },
                        style: ElevatedButton.styleFrom(
                          backgroundColor: Colors.white,
                          foregroundColor: Colors.black,
                          shape: RoundedRectangleBorder(
                            borderRadius: BorderRadius.circular(12),
                          ),
                          elevation: 0,
                        ),
                        child: Text(
                          'Continue with ${authMethod == 'apple' ? 'Apple' : 'Google'}',
                          style: const TextStyle(
                            fontSize: 16,
                            fontWeight: FontWeight.w600,
                          ),
                        ),
                      ),
                    ),

                    const SizedBox(height: 12),

                    // Cancel button
                    SizedBox(
                      width: double.infinity,
                      height: 50,
                      child: TextButton(
                        onPressed: () {
                          Navigator.of(context).pop();
                        },
                        style: TextButton.styleFrom(
                          foregroundColor: Colors.white.withOpacity(0.7),
                          shape: RoundedRectangleBorder(
                            borderRadius: BorderRadius.circular(12),
                          ),
                        ),
                        child: const Text(
                          'Cancel',
                          style: TextStyle(
                            fontSize: 16,
                            fontWeight: FontWeight.w500,
                          ),
                        ),
                      ),
                    ),
                  ],
                ),

                // Bottom padding for safe area
                SizedBox(height: MediaQuery.of(context).padding.bottom),
              ],
            ),
          ),
        ],
      ),
    );
  }

  static void show(
    BuildContext context, {
    required String authMethod,
    required VoidCallback onContinue,
  }) {
    showModalBottomSheet(
      context: context,
      backgroundColor: Colors.transparent,
      isScrollControlled: true,
      builder: (context) => ConsentBottomSheet(
        authMethod: authMethod,
        onContinue: onContinue,
      ),
    );
  }
}
