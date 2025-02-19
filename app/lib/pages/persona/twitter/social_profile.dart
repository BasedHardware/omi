import 'package:flutter/material.dart';
import 'package:friend_private/backend/auth.dart';
import 'package:friend_private/backend/preferences.dart';
import 'package:friend_private/pages/onboarding/wrapper.dart';
import 'package:friend_private/pages/persona/persona_provider.dart';
import 'package:friend_private/pages/persona/twitter/verify_identity_screen.dart';
import 'package:friend_private/utils/other/temp.dart';
import 'package:provider/provider.dart';

class SocialHandleScreen extends StatefulWidget {
  const SocialHandleScreen({
    super.key,
  });

  @override
  State<SocialHandleScreen> createState() => _SocialHandleScreenState();
}

class _SocialHandleScreenState extends State<SocialHandleScreen> {
  late final TextEditingController _controller;
  final _formKey = GlobalKey<FormState>();

  @override
  void initState() {
    super.initState();
    _controller = TextEditingController();
  }

  @override
  void dispose() {
    _controller.dispose();
    super.dispose();
  }

  @override
  Widget build(BuildContext context) {
    return Consumer<PersonaProvider>(builder: (context, provider, child) {
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
            appBar: AppBar(
              backgroundColor: Colors.transparent,
              elevation: 0,
            ),
            body: SafeArea(
              child: Padding(
                padding: const EdgeInsets.symmetric(horizontal: 28.0),
                child: Form(
                  key: _formKey,
                  child: Column(
                    mainAxisSize: MainAxisSize.min,
                    children: [
                      const Spacer(flex: 5),
                      const Center(
                        child: Text(
                          '🤖',
                          style: TextStyle(
                            fontSize: 42,
                          ),
                        ),
                      ),
                      const Spacer(flex: 1),
                      Text(
                        'Let\'s train your clone!\nWhat\'s your X handle?',
                        style: Theme.of(context).textTheme.headlineSmall?.copyWith(
                              fontWeight: FontWeight.bold,
                              color: Colors.white,
                            ),
                        textAlign: TextAlign.center,
                      ),
                      const SizedBox(height: 10),
                      Text(
                        'We will pre-train your Omi clone\nbased on your account\'s activity',
                        style: Theme.of(context).textTheme.titleMedium?.copyWith(
                          color: Colors.white.withOpacity(0.55),
                          shadows: [
                            Shadow(
                              offset: const Offset(0, 1),
                              blurRadius: 3,
                              color: Colors.white.withOpacity(0.25),
                            ),
                          ],
                        ),
                        textAlign: TextAlign.center,
                      ),
                      const Spacer(flex: 2),
                      Container(
                        decoration: BoxDecoration(
                          borderRadius: BorderRadius.circular(12),
                          border: Border.all(
                            color: Colors.white.withOpacity(0.24),
                          ),
                        ),
                        child: TextFormField(
                          controller: _controller,
                          style: const TextStyle(
                            color: Colors.white,
                            fontSize: 16,
                            fontWeight: FontWeight.w500,
                          ),
                          textAlign: TextAlign.left,
                          decoration: InputDecoration(
                            contentPadding: const EdgeInsets.symmetric(horizontal: 16, vertical: 16),
                            border: InputBorder.none,
                            hintText: '@nikshevchenko',
                            hintStyle: TextStyle(
                              color: Colors.white.withOpacity(0.38),
                              fontWeight: FontWeight.bold,
                            ),
                            prefixIcon: Padding(
                              padding: const EdgeInsets.all(14.0),
                              child: Image.asset(
                                'assets/images/x_logo.png',
                                width: 22,
                                height: 22,
                              ),
                            ),
                          ),
                          validator: (value) {
                            if (value == null || value.isEmpty) {
                              return 'Please enter your X handle';
                            }
                            if (value.trim().length < 3 || value.trim().length > 15) {
                              return 'Please enter a valid X handle';
                            }
                            return null;
                          },
                        ),
                      ),
                      const Spacer(flex: 3),
                      TextButton(
                        onPressed: () {
                          FocusScope.of(context).unfocus();
                          SharedPreferencesUtil().hasOmiDevice = true;
                          Navigator.pushReplacement(
                            context,
                            MaterialPageRoute(builder: (context) => const OnboardingWrapper()),
                          );
                        },
                        child: const Text(
                          'I have omi',
                          style: TextStyle(
                            color: Colors.white,
                            fontWeight: FontWeight.bold,
                            fontSize: 18,
                          ),
                        ),
                      ),
                      const Spacer(flex: 1),
                      ElevatedButton(
                        onPressed: () async {
                          FocusScope.of(context).unfocus();
                          if (_formKey.currentState!.validate()) {
                            provider.setIsLoading(true);
                            await signInAnonymously();
                            SharedPreferencesUtil().hasOmiDevice = false;
                            await provider.getTwitterProfile(_controller.text.trim());
                            if (provider.twitterProfile.isNotEmpty) {
                              routeToPage(context, const VerifyIdentityScreen());
                            }
                          }
                        },
                        style: ElevatedButton.styleFrom(
                          backgroundColor: Colors.white.withOpacity(0.12),
                          foregroundColor: Colors.white,
                          minimumSize: const Size(double.infinity, 56),
                          shape: RoundedRectangleBorder(
                            borderRadius: BorderRadius.circular(28),
                          ),
                        ),
                        child: provider.isLoading
                            ? const SizedBox(
                                width: 20,
                                height: 20,
                                child: CircularProgressIndicator(
                                  strokeWidth: 2,
                                  valueColor: AlwaysStoppedAnimation<Color>(Colors.white),
                                ),
                              )
                            : const Text(
                                'Next',
                                style: TextStyle(
                                  fontSize: 18,
                                  fontWeight: FontWeight.bold,
                                ),
                              ),
                      ),
                      const Spacer(flex: 3),
                    ],
                  ),
                ),
              ),
            ),
          ),
        ],
      );
    });
  }
}
