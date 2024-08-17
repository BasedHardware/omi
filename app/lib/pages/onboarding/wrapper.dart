import 'dart:math';

import 'package:flutter/material.dart';
import 'package:friend_private/backend/auth.dart';
import 'package:friend_private/backend/preferences.dart';
import 'package:friend_private/pages/home/page.dart';
import 'package:friend_private/pages/onboarding/auth.dart';
import 'package:friend_private/pages/onboarding/complete/complete.dart';
import 'package:friend_private/pages/onboarding/find_device/page.dart';
import 'package:friend_private/pages/onboarding/permissions/permissions.dart';
import 'package:friend_private/pages/onboarding/welcome/page.dart';
import 'package:friend_private/utils/analytics/mixpanel.dart';
import 'package:friend_private/utils/other/temp.dart';
import 'package:friend_private/widgets/device_widget.dart';

class OnboardingWrapper extends StatefulWidget {
  const OnboardingWrapper({super.key});

  @override
  State<OnboardingWrapper> createState() => _OnboardingWrapperState();
}

class _OnboardingWrapperState extends State<OnboardingWrapper> with TickerProviderStateMixin {
  TabController? _controller;

  @override
  void initState() {
    _controller = TabController(length: 5, vsync: this);
    _controller!.addListener(() => setState(() {}));
    WidgetsBinding.instance.addPostFrameCallback((_) async {
      if (isSignedIn()) { // && !SharedPreferencesUtil().onboardingCompleted
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
          body: Padding(
            padding: const EdgeInsets.symmetric(horizontal: 16),
            child: ListView(
              children: [
                DeviceAnimationWidget(animatedBackground: _controller!.index != -1),
                Center(
                  child: Text(
                    _controller!.index == _controller!.length - 1 ? 'You are all set  🎉' : 'Friend',
                    style: TextStyle(
                        color: Colors.grey.shade200,
                        fontSize: _controller!.index == _controller!.length - 1 ? 28 : 40,
                        fontWeight: FontWeight.w500),
                  ),
                ),
                const SizedBox(height: 24),
                _controller!.index == 3 || _controller!.index == 4 || _controller!.index == 5
                    ? const SizedBox()
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
                  height: max(MediaQuery.of(context).size.height - 500 - 64, 305),
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
                              routeToPage(context, const HomePageWrapper(), replace: true);
                            } else {
                              _goNext();
                            }
                          },
                        ),
                        PermissionsPage(
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
                          skipDevice: () {
                            _controller!.animateTo(_controller!.index + 2);
                            MixpanelManager().onboardingStepICompleted('Welcome');
                          },
                        ),
                        FindDevicesPage(
                          goNext: () {
                            _goNext();
                            MixpanelManager().onboardingStepICompleted('Find Devices');
                          },
                        ),
                        CompletePage(
                          goNext: () {
                            routeToPage(context, const HomePageWrapper(), replace: true);
                            MixpanelManager().onboardingStepICompleted('Finalize');
                            MixpanelManager().onboardingCompleted();
                          },
                        ),
                      ],
                    ),
                  ),
                ),
              ],
            ),
          )),
    );
  }
}
