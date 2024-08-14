import 'dart:math';

import 'package:flutter/material.dart';
import 'package:friend_private/pages/home/page.dart';
import 'package:friend_private/pages/onboarding/complete/complete.dart';
import 'package:friend_private/pages/onboarding/find_device/page.dart';
import 'package:friend_private/pages/onboarding/import/existing.dart';
import 'package:friend_private/pages/onboarding/import/import.dart';
import 'package:friend_private/pages/onboarding/welcome/page.dart';
import 'package:friend_private/utils/temp.dart';
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
                DeviceAnimationWidget(animatedBackground: _controller!.index != 0),
                SizedBox(
                  height: max(MediaQuery.of(context).size.height - 400 - 64, 300),
                  child: Padding(
                    padding: const EdgeInsets.only(bottom: 64),
                    child: TabBarView(
                      controller: _controller,
                      physics: const NeverScrollableScrollPhysics(),
                      children: [
                        // TODO: if connected already, stop animation and display battery

                        WelcomePage(
                          goNext: _goNext,
                          skipDevice: () => _controller!.animateTo(2),
                        ),
                        FindDevicesPage(
                          goNext: _goNext,
                        ),
                        HasBackupPage(
                          goNext: _goNext,
                          onSkip: () => _controller!.animateTo(_controller!.index + 2),
                        ),
                        ImportBackupPage(
                          goNext: () => routeToPage(context, const HomePageWrapper(), replace: true),
                          goBack: () {
                            _controller!.animateTo(_controller!.index - 1);
                            FocusScope.of(context).unfocus();
                          },
                        ),
                        CompletePage(
                          goNext: () => routeToPage(context, const HomePageWrapper(), replace: true),
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
