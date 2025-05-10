import 'package:firebase_auth/firebase_auth.dart';
import 'package:flutter/material.dart';
import 'package:omi/backend/auth.dart';
import 'package:omi/backend/preferences.dart';
import 'package:omi/gen/assets.gen.dart';
import 'package:omi/pages/onboarding/wrapper.dart';
import 'package:omi/pages/persona/persona_provider.dart';
import 'package:omi/pages/persona/twitter/verify_identity_screen.dart';
import 'package:omi/utils/other/temp.dart';
import 'package:posthog_flutter/posthog_flutter.dart';
import 'package:provider/provider.dart';

class SocialHandleScreen extends StatefulWidget {
  final PersonaProfileRouting routing;

  const SocialHandleScreen({
    super.key,
    this.routing = PersonaProfileRouting.no_device,
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
      return GestureDetector(
        onTap: () {
          FocusScope.of(context).unfocus();
        },
        child: Stack(
          children: [
            // Background image
            Positioned.fill(
              child: Image.asset(
                Assets.images.newBackground.path,
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
                        const Spacer(flex: 1),
                        Text(
                          'What\'s your X handle?',
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
                        TextFormField(
                          controller: _controller,
                          style: const TextStyle(
                            color: Colors.white,
                            fontSize: 16,
                            fontWeight: FontWeight.w500,
                          ),
                          textAlign: TextAlign.left,
                          decoration: InputDecoration(
                            contentPadding: const EdgeInsets.symmetric(horizontal: 16, vertical: 16),
                            border: OutlineInputBorder(
                              borderRadius: BorderRadius.circular(12),
                              borderSide: BorderSide(
                                color: Colors.white.withOpacity(0.24),
                                width: 1,
                              ),
                            ),
                            enabledBorder: OutlineInputBorder(
                              borderRadius: BorderRadius.circular(12),
                              borderSide: BorderSide(
                                color: Colors.white.withOpacity(0.24),
                                width: 1,
                              ),
                            ),
                            focusedBorder: OutlineInputBorder(
                              borderRadius: BorderRadius.circular(12),
                              borderSide: BorderSide(
                                color: Colors.white.withOpacity(0.4),
                                width: 1,
                              ),
                            ),
                            errorBorder: OutlineInputBorder(
                              borderRadius: BorderRadius.circular(12),
                              borderSide: BorderSide(
                                color: Colors.white.withOpacity(0.24),
                                width: 1,
                              ),
                            ),
                            focusedErrorBorder: OutlineInputBorder(
                              borderRadius: BorderRadius.circular(12),
                              borderSide: BorderSide(
                                color: Colors.white.withOpacity(0.4),
                                width: 1,
                              ),
                            ),
                            hintText: '@nikshevchenko',
                            hintStyle: TextStyle(
                              color: Colors.white.withOpacity(0.38),
                              fontWeight: FontWeight.bold,
                            ),
                            prefixIcon: Padding(
                              padding: const EdgeInsets.all(14.0),
                              child: Image.asset(
                                Assets.images.xLogo.path,
                                width: 22,
                                height: 22,
                              ),
                            ),
                            errorStyle: TextStyle(
                              color: Colors.white.withOpacity(0.55),
                              fontSize: 13,
                              height: 1,
                            ),
                            errorMaxLines: 2,
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
                        const SizedBox(height: 8),
                        const Spacer(flex: 5),
                        ElevatedButton(
                          onPressed: () async {
                            FocusScope.of(context).unfocus();
                            if (_formKey.currentState!.validate()) {
                              provider.setIsLoading(true);
                              if (FirebaseAuth.instance.currentUser == null) {
                                debugPrint('User is not signed in, signing in anonymously');
                                await signInAnonymously();
                              }
                              var handle = _controller.text.trim();
                              await Posthog().capture(
                                eventName: 'x_handle_submitted',
                                properties: {'handle': handle, 'uid': FirebaseAuth.instance.currentUser?.uid ?? ''},
                              );
                              SharedPreferencesUtil().hasOmiDevice = false;
                              Provider.of<PersonaProvider>(context, listen: false).setRouting(widget.routing);
                              await provider.getTwitterProfile(handle);
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
                        SizedBox(height: MediaQuery.of(context).textScaleFactor > 1.0 ? 18 : 32),
                        FirebaseAuth.instance.currentUser == null || FirebaseAuth.instance.currentUser!.isAnonymous
                            ? TextButton(
                                onPressed: () async {
                                  FocusScope.of(context).unfocus();
                                  await Posthog().capture(
                                    eventName: 'pressed_i_have_omi',
                                    properties: {
                                      'username': _controller.text,
                                    },
                                  );

                                  routeToPage(context, OnboardingWrapper());
                                },
                                child: const Text(
                                  'Connect Omi Device',
                                  style: TextStyle(
                                    color: Colors.white,
                                    fontWeight: FontWeight.bold,
                                    fontSize: 18,
                                  ),
                                ),
                              )
                            : const SizedBox(),
                        const Spacer(flex: 1),
                      ],
                    ),
                  ),
                ),
              ),
            ),
          ],
        ),
      );
    });
  }
}
