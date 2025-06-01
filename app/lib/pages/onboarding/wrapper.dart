import 'dart:math';

import 'package:firebase_auth/firebase_auth.dart';
import 'package:flutter/material.dart';
import 'package:omi/backend/auth.dart';
import 'package:omi/backend/preferences.dart';
import 'package:omi/backend/schema/bt_device/bt_device.dart';
import 'package:omi/pages/home/page.dart';
import 'package:omi/pages/onboarding/auth.dart';
import 'package:omi/pages/onboarding/find_device/page.dart';
import 'package:omi/pages/onboarding/name/name_widget.dart';
import 'package:omi/pages/onboarding/permissions/permissions_widget.dart';
import 'package:omi/pages/onboarding/primary_language/primary_language_widget.dart';
import 'package:omi/pages/onboarding/speech_profile_widget.dart';
import 'package:omi/pages/onboarding/welcome/page.dart';
import 'package:omi/providers/home_provider.dart';
import 'package:omi/providers/onboarding_provider.dart';
import 'package:omi/services/services.dart';
import 'package:omi/utils/analytics/intercom.dart';
import 'package:omi/utils/analytics/mixpanel.dart';
import 'package:omi/utils/other/temp.dart';
import 'package:omi/widgets/device_widget.dart';
import 'package:provider/provider.dart';

class OnboardingWrapper extends StatefulWidget {
  const OnboardingWrapper({super.key});

  @override
  State<OnboardingWrapper> createState() => _OnboardingWrapperState();
}

class _OnboardingWrapperState extends State<OnboardingWrapper> with TickerProviderStateMixin {
  // Onboarding page indices
  static const int kAuthPage = 0;
  static const int kNamePage = 1;
  static const int kPrimaryLanguagePage = 2;
  static const int kPermissionsPage = 3;
  static const int kWelcomePage = 4;
  static const int kFindDevicesPage = 5;
  static const int kSpeechProfilePage = 6; // Now always the last index

  // Special index values used in comparisons
  static const List<int> kHiddenHeaderPages = [-1, 5, 6];

  TabController? _controller;
  bool get hasSpeechProfile => SharedPreferencesUtil().hasSpeakerProfile;

  @override
  void initState() {
    _controller = TabController(length: 7, vsync: this);
    _controller!.addListener(() => setState(() {}));
    WidgetsBinding.instance.addPostFrameCallback((_) async {
      if (mounted) {
        context.read<OnboardingProvider>().updatePermissions();
      }

      if (isSignedIn()) {
        // && !SharedPreferencesUtil().onboardingCompleted
        if (mounted) {
          context.read<HomeProvider>().setupHasSpeakerProfile();
          if (SharedPreferencesUtil().onboardingCompleted) {
            routeToPage(context, const HomePageWrapper(), replace: true);
          } else {
            _controller!.animateTo(kNamePage);
          }
        }
      }
      // If not signed in, it stays at the Auth page (index 0)
    });
    super.initState();
  }

  @override
  void dispose() {
    _controller?.dispose();
    super.dispose();
  }

  _goNext() {
    if (_controller!.index < _controller!.length - 1) {
      _controller!.animateTo(_controller!.index + 1);
    }
  }

  // TODO: use connection directly
  Future<BleAudioCodec> _getAudioCodec(String deviceId) async {
    var connection = await ServiceManager.instance().device.ensureConnection(deviceId);
    if (connection == null) {
      return BleAudioCodec.pcm8;
    }
    return connection.getAudioCodec();
  }

  @override
  Widget build(BuildContext context) {
    List<Widget> pages = [
      AuthComponent(
        onSignIn: () {
          SharedPreferencesUtil().hasOmiDevice = true;
          SharedPreferencesUtil().verifiedPersonaId = null;
          MixpanelManager().onboardingStepCompleted('Auth');
          context.read<HomeProvider>().setupHasSpeakerProfile();
          IntercomManager.instance.intercom.loginIdentifiedUser(
            userId: SharedPreferencesUtil().uid,
          );
          if (SharedPreferencesUtil().onboardingCompleted) {
            routeToPage(context, const HomePageWrapper(), replace: true);
          } else {
            _goNext(); // Go to Name page
          }
        },
      ),
      NameWidget(goNext: () {
        _goNext(); // Go to Primary Language page
        IntercomManager.instance.updateUser(
          FirebaseAuth.instance.currentUser!.email,
          FirebaseAuth.instance.currentUser!.displayName,
          FirebaseAuth.instance.currentUser!.uid,
        );
        MixpanelManager().onboardingStepCompleted('Name');
      }),
      PrimaryLanguageWidget(goNext: () {
        _goNext(); // Go to Permissions page
        MixpanelManager().onboardingStepCompleted('Primary Language');
      }),
      PermissionsWidget(
        goNext: () {
          _goNext(); // Go to Welcome page
          MixpanelManager().onboardingStepCompleted('Permissions');
        },
      ),
      WelcomePage(
        goNext: () {
          _goNext(); // Go to Find Devices page
          MixpanelManager().onboardingStepCompleted('Welcome');
        },
      ),
      FindDevicesPage(
        isFromOnboarding: true,
        onSkip: () {
          // Skipping device finding means skipping speech profile too
          routeToPage(context, const HomePageWrapper(), replace: true);
        },
        goNext: () async {
          var provider = context.read<OnboardingProvider>();
          MixpanelManager().onboardingStepCompleted('Find Devices');

          if (hasSpeechProfile) {
            routeToPage(context, const HomePageWrapper(), replace: true);
          } else {
            var codec = await _getAudioCodec(provider.deviceId);
            if (codec.isOpusSupported()) {
              _goNext(); // Go to Speech Profile page
            } else {
              // Device selected, but not Opus, skip speech profile
              routeToPage(context, const HomePageWrapper(), replace: true);
            }
          }
        },
      ),
      SpeechProfileWidget(
        goNext: () {
          routeToPage(context, const HomePageWrapper(), replace: true);
          MixpanelManager().onboardingStepCompleted('Speech Profile');
        },
        onSkip: () {
          routeToPage(context, const HomePageWrapper(), replace: true);
          MixpanelManager().onboardingStepCompleted('Speech Profile Skipped');
        },
      ),
    ];

    return GestureDetector(
      onTap: () => FocusScope.of(context).unfocus(),
      child: Scaffold(
        backgroundColor: Theme.of(context).colorScheme.primary,
        body: SingleChildScrollView(
          child: Stack(
            children: [
              Padding(
                padding: const EdgeInsets.symmetric(horizontal: 16),
                child: ListView(
                  shrinkWrap: true,
                  physics: const NeverScrollableScrollPhysics(),
                  children: [
                    DeviceAnimationWidget(animatedBackground: _controller!.index != -1),
                    const SizedBox(height: 24),
                    kHiddenHeaderPages.contains(_controller?.index)
                        ? const SizedBox.shrink()
                        : Padding(
                            padding: const EdgeInsets.symmetric(horizontal: 16),
                            child: Text(
                              'Your personal growth journey with AI that listens to your every word.',
                              style: TextStyle(color: Colors.grey.shade300, fontSize: 24),
                              textAlign: TextAlign.center,
                            ),
                          ),
                    SizedBox(
                      height: (_controller!.index == kFindDevicesPage || _controller!.index == kSpeechProfilePage)
                          ? max(MediaQuery.of(context).size.height - 500 - 10,
                              maxHeightWithTextScale(context, _controller!.index))
                          : max(MediaQuery.of(context).size.height - 500 - 30,
                              maxHeightWithTextScale(context, _controller!.index)),
                      child: Padding(
                        padding: EdgeInsets.only(bottom: MediaQuery.sizeOf(context).height <= 700 ? 10 : 64),
                        child: TabBarView(
                          controller: _controller,
                          physics: const NeverScrollableScrollPhysics(),
                          children: pages,
                        ),
                      ),
                    ),
                  ],
                ),
              ),
              if (_controller!.index == kWelcomePage)
                Padding(
                  padding: const EdgeInsets.fromLTRB(0, 40, 16, 0),
                  child: Align(
                    alignment: Alignment.topRight,
                    child: TextButton(
                      onPressed: () {
                        if (_controller!.index == kPermissionsPage) {
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
                  ),
                ),
              if (_controller!.index > kNamePage)
                Padding(
                  padding: const EdgeInsets.fromLTRB(16, 40, 0, 0),
                  child: Align(
                    alignment: Alignment.topLeft,
                    child: TextButton(
                      onPressed: () {
                        if (_controller!.index > kNamePage) {
                          _controller!.animateTo(_controller!.index - 1);
                        }
                      },
                      child: Text(
                        'Back',
                        style: TextStyle(color: Colors.grey.shade200),
                      ),
                    ),
                  ),
                ),
              if (_controller!.index != kAuthPage)
                Padding(
                  padding: const EdgeInsets.fromLTRB(16, 56, 16, 0),
                  child: Row(
                    mainAxisAlignment: MainAxisAlignment.center,
                    children: List.generate(
                      6,
                      (index) {
                        int pageIndex = index + 1; // Name=1, Lang=2, ..., Speech=6
                        return Container(
                          margin: const EdgeInsets.symmetric(horizontal: 4.0),
                          width: pageIndex == _controller!.index ? 12.0 : 8.0,
                          height: pageIndex == _controller!.index ? 12.0 : 8.0,
                          decoration: BoxDecoration(
                            color: pageIndex <= _controller!.index
                                ? Theme.of(context).colorScheme.secondary
                                : Colors.grey.shade400,
                            shape: BoxShape.circle,
                          ),
                        );
                      },
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

double maxHeightWithTextScale(BuildContext context, int index) {
  double textScaleFactor = MediaQuery.of(context).textScaleFactor;
  if (textScaleFactor > 1.0) {
    if (index == _OnboardingWrapperState.kAuthPage) {
      return 200;
    } else {
      return 405;
    }
  } else {
    return 305;
  }
}
