import 'package:flutter/material.dart';

/// Tallest a bottom-anchored onboarding step block may be.
///
/// The wrapper's persistent backdrops — the device + glow behind splash,
/// sign-in and data & privacy, and the dot ring behind the later steps — are
/// centred just above the vertical midpoint and reach down to roughly half
/// the screen height. A step's text and buttons rise from the bottom, so
/// anything taller than the lower half climbs into the artwork. Cap the block
/// here and scroll inside it instead.
double onboardingBottomBlockMaxHeight(BuildContext context) {
  final size = MediaQuery.sizeOf(context);
  return size.height * 0.5 - 8;
}

/// Sizes a bottom-block's copy to the height it is given without scrolling
/// and without giving up the full width: the copy renders at its natural
/// size when it fits, and when it does not, only the text scale is reduced
/// (iteratively, from a post-frame measurement) until the block fits. Lines
/// keep wrapping at the full block width, so nothing shrinks into a narrow
/// column. Wrap the copy only — buttons stay outside at full size.
class OnboardingFitToHeight extends StatefulWidget {
  final Widget child;

  const OnboardingFitToHeight({super.key, required this.child});

  @override
  State<OnboardingFitToHeight> createState() => _OnboardingFitToHeightState();
}

class _OnboardingFitToHeightState extends State<OnboardingFitToHeight> {
  static const double _minTextScale = 0.6;

  final GlobalKey _contentKey = GlobalKey();
  double _textScale = 1.0;
  double? _fittedWidth;

  void _measure(double maxHeight) {
    if (!mounted) return;
    final box = _contentKey.currentContext?.findRenderObject();
    if (box is! RenderBox || !box.hasSize) return;
    final height = box.size.height;
    final overflows = height > maxHeight + 0.5;
    final hasSlack = _textScale < 1.0 && height < maxHeight - 0.5;
    if (!overflows && !hasSlack) return;
    final next = (_textScale * maxHeight / height).clamp(_minTextScale, 1.0);
    if ((next - _textScale).abs() < 0.005) return;
    setState(() => _textScale = next);
  }

  @override
  Widget build(BuildContext context) {
    return LayoutBuilder(
      builder: (context, constraints) {
        final width = constraints.maxWidth;
        final maxHeight = constraints.maxHeight;
        // A new width (rotation, first layout) restarts from the natural size
        // because wrapping changes. A height-only change (a button swapping to
        // its loading state, the keyboard) keeps the current scale and lets the
        // measurement below shrink or grow it — restarting at 1.0 there showed
        // one frame of oversized copy before the fit caught up.
        if (_fittedWidth != width) {
          _fittedWidth = width;
          _textScale = 1.0;
        }
        if (maxHeight.isFinite) {
          WidgetsBinding.instance.addPostFrameCallback((_) => _measure(maxHeight));
        }
        final mediaQuery = MediaQuery.of(context);
        return ClipRect(
          child: OverflowBox(
            alignment: Alignment.bottomCenter,
            minHeight: 0,
            maxHeight: double.infinity,
            child: MediaQuery(
              data: mediaQuery.copyWith(
                textScaler: TextScaler.linear(mediaQuery.textScaler.scale(1.0) * _textScale),
              ),
              child: KeyedSubtree(
                key: _contentKey,
                child: SizedBox(width: width, child: widget.child),
              ),
            ),
          ),
        );
      },
    );
  }
}

/// Step heading that always renders on one line: 28px bold Manrope, scaled
/// down (never wrapped) when a locale or narrow screen would otherwise break
/// it across two lines.
class OnboardingStepTitle extends StatelessWidget {
  final String text;

  const OnboardingStepTitle(this.text, {super.key});

  @override
  Widget build(BuildContext context) {
    return FittedBox(
      fit: BoxFit.scaleDown,
      child: Text(
        text,
        maxLines: 1,
        style: const TextStyle(
          color: Colors.white,
          fontSize: 28,
          fontWeight: FontWeight.bold,
          height: 1.2,
          fontFamily: 'Manrope',
        ),
        textAlign: TextAlign.center,
      ),
    );
  }
}
