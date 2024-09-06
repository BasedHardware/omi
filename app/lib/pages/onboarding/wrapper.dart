import 'dart:math';

import 'package:flutter/material.dart';
import 'package:friend_private/backend/auth.dart';
import 'package:friend_private/backend/preferences.dart';
import 'package:friend_private/backend/schema/bt_device.dart';
import 'package:friend_private/pages/home/page.dart';
import 'package:friend_private/pages/onboarding/auth.dart';
import 'package:friend_private/pages/onboarding/find_device/page.dart';
import 'package:friend_private/pages/onboarding/memory_created_widget.dart';
import 'package:friend_private/pages/onboarding/name/name_widget.dart';
import 'package:friend_private/pages/onboarding/permissions/notification_permission.dart';
import 'package:friend_private/pages/onboarding/speech_profile_widget.dart';
import 'package:friend_private/pages/onboarding/welcome/page.dart';
import 'package:friend_private/providers/onboarding_provider.dart';
import 'package:friend_private/providers/speech_profile_provider.dart';
import 'package:friend_private/utils/analytics/mixpanel.dart';
import 'package:friend_private/utils/ble/communication.dart';
import 'package:friend_private/utils/other/temp.dart';
import 'package:friend_private/widgets/device_widget.dart';
import 'package:provider/provider.dart';

class OnboardingWrapper extends StatefulWidget {
  const OnboardingWrapper({super.key});

  @override
  State<OnboardingWrapper> createState() => _OnboardingWrapperState();
}

class _OnboardingWrapperState extends State<OnboardingWrapper> with TickerProviderStateMixin {
  TabController? _controller;

  @override
  void initState() {
    _controller = TabController(length: 7, vsync: this);
    _controller!.addListener(() => setState(() {}));
    WidgetsBinding.instance.addPostFrameCallback((_) async {
      if (isSignedIn()) {
        // && !SharedPreferencesUtil().onboardingCompleted
        _goNext();
      }
    });
    super.initState();
  }

  @override
  void dispose() {
    _controller?.dispose();
    super.dispose();
  }

  _goNext() => _controller!.animateTo(_controller!.index + 1);

  @override
  Widget build(BuildContext context) {
    return GestureDetector(
      onTap: () => FocusScope.of(context).unfocus(),
      child: Scaffold(
        backgroundColor: Theme.of(context).colorScheme.primary,
        appBar: AppBar(
          backgroundColor: Theme.of(context).colorScheme.primary,
          elevation: 0,
          actions: [
            if (_controller!.index == 2 || _controller!.index == 3)
              TextButton(
                onPressed: () {
                  if (_controller!.index == 2) {
                    _controller!.animateTo(_controller!.index + 1);
                  } else {
                    routeToPage(context, const HomePageWrapper(), replace: true);
                  }
                },
                child: Text(
                  'Skip',
                  style: TextStyle(color: Colors.grey.shade200),
                ),
              ),
          ],
        ),
        body: Padding(
          padding: const EdgeInsets.symmetric(horizontal: 16),
          child: ListView(
            children: [
              DeviceAnimationWidget(animatedBackground: _controller!.index != -1),
              _controller!.index == 6 || _controller!.index == 7
                  ? const SizedBox()
                  : Center(
                      child: Text(
                        'Omi',
                        style: TextStyle(
                            color: Colors.grey.shade200,
                            fontSize: _controller!.index == _controller!.length - 1 ? 28 : 40,
                            fontWeight: FontWeight.w500),
                      ),
                    ),
              const SizedBox(height: 24),
              [-1, 5, 6, 7].contains(_controller?.index)
                  ? const SizedBox(
                      height: 0,
                    )
                  : Padding(
                      padding: const EdgeInsets.symmetric(horizontal: 16),
                      child: Text(
                        _controller!.index == _controller!.length - 1
                            ? 'Your personal growth journey with AI that listens to your every word.'
                            : 'Your personal growth journey with AI that listens to your every word.',
                        style: TextStyle(color: Colors.grey.shade300, fontSize: 16),
                        textAlign: TextAlign.center,
                      ),
                    ),
              SizedBox(
                height: (_controller!.index == 5 || _controller!.index == 6 || _controller!.index == 7)
                    ? max(MediaQuery.of(context).size.height - 500 - 10, 305)
                    : max(MediaQuery.of(context).size.height - 500 - 60, 305),
                child: Padding(
                  padding: EdgeInsets.only(bottom: MediaQuery.sizeOf(context).height <= 700 ? 10 : 64),
                  child: TabBarView(
                    controller: _controller,
                    physics: const NeverScrollableScrollPhysics(),
                    children: [
                      // TODO: if connected already, stop animation and display battery
                      AuthComponent(
                        onSignIn: () {
                          MixpanelManager().onboardingStepICompleted('Auth');
                          if (SharedPreferencesUtil().onboardingCompleted) {
                            // previous users
                            // Not needed anymore, because AuthProvider already does this
                            // routeToPage(context, const HomePageWrapper(), replace: true);
                          } else {
                            _goNext();
                          }
                        },
                      ),
                      NameWidget(
                        goNext: _goNext,
                      ),
                      NotificationPermissionWidget(
                        goNext: () {
                          _goNext();
                          MixpanelManager().onboardingStepICompleted('Permissions');
                        },
                      ),
                      WelcomePage(
                        goNext: () {
                          _goNext();
                          MixpanelManager().onboardingStepICompleted('Welcome');
                        },
                      ),
                      FindDevicesPage(
                        isFromOnboarding: true,
                        onSkip: () {
                          routeToPage(context, const HomePageWrapper(), replace: true);
                        },
                        goNext: () async {
                          var provider = context.read<OnboardingProvider>();
                          if (SharedPreferencesUtil().hasSpeakerProfile) {
                            // previous users
                            routeToPage(context, const HomePageWrapper(), replace: true);
                          } else {
                            if (provider.deviceId.isEmpty) {
                              _goNext();
                            } else {
                              var codec = await getAudioCodec(provider.deviceId);
                              if (codec == BleAudioCodec.opus) {
                                _goNext();
                              } else {
                                routeToPage(context, const HomePageWrapper(), replace: true);
                              }
                            }
                          }

                          MixpanelManager().onboardingStepICompleted('Find Devices');
                        },
                      ),
                      SpeechProfileWidget(
                        goNext: () {
                          if (context.read<SpeechProfileProvider>().memory == null) {
                            _controller!.animateTo(_controller!.index + 2);
                          } else {
                            _goNext();
                          }
                          MixpanelManager().onboardingStepICompleted('Speech Profile');
                        },
                        onSkip: () {
                          routeToPage(context, const HomePageWrapper(), replace: true);
                        },
                      ),
                      MemoryCreatedWidget(
                        goNext: () {
                          // _goNext();
                          MixpanelManager().onboardingStepICompleted('Memory Created');
                        },
                      ),
                      // CompletePage(
                      //   goNext: () {
                      //     routeToPage(context, const HomePageWrapper(), replace: true);
                      //     MixpanelManager().onboardingStepICompleted('Finalize');
                      //     MixpanelManager().onboardingCompleted();
                      //   },
                      // ),
                    ],
                  ),
                ),
              ),
            ],
          ),
        ),
      ),
    );
  }
}
