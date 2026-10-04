import 'package:flutter/material.dart';

import 'package:omi/ui/ui.dart';
import 'package:omi/mobile/native_ui/ios_native_home.dart';
import 'package:omi/mobile/native_ui/ios_native_surface.dart';
import 'package:omi/mobile/native_ui/native_navigation_chrome.dart';
import 'package:omi/utils/l10n_extensions.dart';

/// Height of the navigation row (progress dots and back button) below the status bar: the dots'
/// top gap plus one tap target.
const double kOnboardingChromeHeight = OmiSpacing.md + kOmiMinTapTarget;

/// The host owns space for navigation above steps that start at the top of the screen.
/// Bottom-card steps keep their navigation over the background artwork, but their content still
/// clears it: the step gets a [MediaQuery] whose top padding includes [kOnboardingChromeHeight], so
/// its own [SafeArea] starts below the navigation while backgrounds bleed to the top edge.
class OnboardingStepLayout extends StatefulWidget {
  const OnboardingStepLayout(
      {super.key,
      required this.child,
      required this.reserveHeader,
      this.progress,
      this.onBack,
      this.nativeNavigation = false,
      this.nativeProgress = ''});

  final Widget child;
  final bool reserveHeader;
  final Widget? progress;
  final VoidCallback? onBack;
  final bool nativeNavigation;
  final String nativeProgress;

  @override
  State<OnboardingStepLayout> createState() => _OnboardingStepLayoutState();
}

class _OnboardingStepLayoutState extends State<OnboardingStepLayout> {
  // Parent rebuilds must not unmount the active capture/review owner while
  // a fresh platform-support reply is pending.
  late final Future<bool> _nativeSupported = supportsIosSwiftUi();

  @override
  Widget build(BuildContext context) {
    if (widget.nativeNavigation && iosSwiftUiEnabled) {
      return FutureBuilder<bool>(
          future: _nativeSupported,
          builder: (context, support) {
            if (support.connectionState != ConnectionState.done) return const OmiLoadingState();
            if (support.data != true) return _classic(context, widget.child);
            return NativeNavigationChrome(
                sections: [
                  if (widget.nativeProgress.isNotEmpty)
                    NativeSection('onboarding_progress', [
                      NativeRow('onboarding_progress_label', widget.nativeProgress, kind: 'label'),
                    ])
                ],
                toolbar: [
                  if (widget.onBack != null)
                    NativeRow('onboarding_back', context.l10n.back,
                        symbol: 'chevron.left', action: (_) => widget.onBack!())
                ],
                wrapFallback: (fallback) => NativeNavigationChrome(enabled: false, child: _classic(context, fallback)),
                child: widget.child);
          });
    }
    return _classic(context, widget.child);
  }

  Widget _classic(BuildContext context, Widget content) {
    final chrome = Stack(
      children: [
        if (widget.progress != null)
          Padding(
            padding: const EdgeInsets.only(top: OmiSpacing.md),
            child: widget.progress!,
          ),
        if (widget.onBack != null)
          Padding(
            padding: const EdgeInsets.only(left: OmiSpacing.xs, top: OmiSpacing.xxs),
            child: Align(
              alignment: Alignment.topLeft,
              child: OmiBackButton.circled(key: const Key('onboarding_back'), onPressed: widget.onBack),
            ),
          ),
      ],
    );
    if (widget.reserveHeader) {
      return Column(
        children: [
          SafeArea(
            bottom: false,
            child: SizedBox(height: kOnboardingChromeHeight, child: chrome),
          ),
          Expanded(
            child: MediaQuery.removePadding(context: context, removeTop: true, child: content),
          ),
        ],
      );
    }
    if (widget.progress == null && widget.onBack == null) return content;
    final media = MediaQuery.of(context);
    return Stack(
      children: [
        MediaQuery(
          data: media.copyWith(padding: media.padding.copyWith(top: media.padding.top + kOnboardingChromeHeight)),
          child: content,
        ),
        SafeArea(child: chrome),
      ],
    );
  }
}
