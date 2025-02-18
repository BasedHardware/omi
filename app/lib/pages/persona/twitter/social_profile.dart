import 'package:flutter/material.dart';
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
            child: Column(
              children: [
                Expanded(
                  child: SingleChildScrollView(
                    child: Padding(
                      padding: const EdgeInsets.symmetric(horizontal: 24.0),
                      child: Form(
                        key: _formKey,
                        child: Column(
                          children: [
                            const SizedBox(height: 20),
                            const Center(
                              child: Text(
                                '🤖',
                                style: TextStyle(
                                  fontSize: 42,
                                ),
                              ),
                            ),
                            const SizedBox(height: 16),
                            Text(
                              'Let\'s train your clone!\nWhat\'s your Twitter handle?',
                              style: Theme.of(context).textTheme.headlineSmall?.copyWith(
                                fontWeight: FontWeight.bold,
                                color: Colors.white,
                                shadows: [
                                  Shadow(
                                    offset: const Offset(0, 1),
                                    blurRadius: 15,
                                    color: Colors.white.withOpacity(1),
                                  ),
                                  Shadow(
                                    offset: const Offset(0, 0),
                                    blurRadius: 15,
                                    color: Colors.white.withOpacity(0.3),
                                  ),
                                ],
                              ),
                              textAlign: TextAlign.center,
                            ),
                            const SizedBox(height: 8),
                            Text(
                              'We will pre-train your Omi clone\nbased on your account\'s activity',
                              style: Theme.of(context).textTheme.titleMedium?.copyWith(
                                color: Colors.white.withOpacity(0.8),
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
                            const SizedBox(height: 32),
                            Container(
                              decoration: BoxDecoration(
                                color: Colors.white.withOpacity(0.1),
                                borderRadius: BorderRadius.circular(12),
                                border: Border.all(
                                  color: Colors.white.withOpacity(0.2),
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
                                  hintStyle: TextStyle(color: Colors.white.withOpacity(0.5)),
                                  prefixIcon: Padding(
                                    padding: const EdgeInsets.all(12.0),
                                    child: Image.asset(
                                      'assets/images/x_logo.png',
                                      width: 24,
                                      height: 24,
                                    ),
                                  ),
                                ),
                                validator: (value) {
                                  if (value == null || value.isEmpty) {
                                    return 'Please enter your Twitter handle';
                                  }
                                  return null;
                                },
                              ),
                            ),
                          ],
                        ),
                      ),
                    ),
                  ),
                ),
                Padding(
                  padding: const EdgeInsets.fromLTRB(24, 0, 24, 40),
                  child: ElevatedButton(
                    onPressed: () async {
                      if (_formKey.currentState!.validate()) {
                        await context.read<PersonaProvider>().getTwitterProfile(_controller.text.trim());
                        if (context.read<PersonaProvider>().twitterProfile.isNotEmpty) {
                          // await Preferences().setTwitterHandle(_controller.text.trim());
                          routeToPage(context, VerifyIdentityScreen());
                        }
                      }
                    },
                    style: ElevatedButton.styleFrom(
                      backgroundColor: Colors.grey[900],
                      foregroundColor: Colors.white,
                      minimumSize: const Size(double.infinity, 56),
                      shape: RoundedRectangleBorder(
                        borderRadius: BorderRadius.circular(28),
                      ),
                    ),
                    child: const Text(
                      'Next',
                      style: TextStyle(
                        fontSize: 16,
                        fontWeight: FontWeight.bold,
                      ),
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
