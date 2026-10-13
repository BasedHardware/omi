import 'package:flutter/material.dart';

import 'package:omi/ui/ui.dart';

/// A first-run step without artwork: the title (and an optional line under it) at the top, the
/// step's [body] below, and the step's [action] pinned to the bottom, above the keyboard when it is
/// up. The host's [MediaQuery] top padding already clears the progress line and back button.
///
/// [headingTop] moves the title down from the top, e.g. to sit just above a system permission
/// prompt that opens in the middle of the screen.
///
/// With [centered], the title stays at the top and the body sits in the middle of the space between
/// the title and the action, staying centred as the keyboard opens and closes.
class OnboardingPlainStep extends StatelessWidget {
  const OnboardingPlainStep({
    super.key,
    required this.title,
    this.subtitle,
    required this.body,
    this.action,
    this.centered = false,
    this.headingTop = 0,
  });

  final String title;
  final String? subtitle;
  final Widget body;
  final Widget? action;
  final bool centered;
  final double headingTop;

  @override
  Widget build(BuildContext context) {
    final heading = <Widget>[
      Semantics(header: true, child: Text(title, style: OmiType.title1, textAlign: TextAlign.center)),
      if (subtitle != null) ...[
        const SizedBox(height: OmiSpacing.xs),
        Text(subtitle!, style: OmiType.subhead.copyWith(color: OmiColors.textSecondary), textAlign: TextAlign.center),
      ],
    ];
    final Widget content = Column(
      crossAxisAlignment: CrossAxisAlignment.stretch,
      children: [
        if (headingTop > 0) SizedBox(height: headingTop),
        ...heading,
        const SizedBox(height: OmiSpacing.xxl),
        Expanded(
          child: centered
              // The body alone sits in the middle of the space between the title and the action.
              ? LayoutBuilder(
                  builder: (context, constraints) => SingleChildScrollView(
                    child: ConstrainedBox(
                      constraints: BoxConstraints(minHeight: constraints.maxHeight),
                      child: Column(
                        mainAxisAlignment: MainAxisAlignment.center,
                        crossAxisAlignment: CrossAxisAlignment.stretch,
                        children: [body],
                      ),
                    ),
                  ),
                )
              : SingleChildScrollView(child: body),
        ),
      ],
    );
    return SafeArea(
      child: Padding(
        padding: const EdgeInsets.fromLTRB(OmiSpacing.xl, OmiSpacing.lg, OmiSpacing.xl, OmiSpacing.sm),
        child: Column(
          crossAxisAlignment: CrossAxisAlignment.stretch,
          children: [
            Expanded(child: content),
            if (action != null) ...[const SizedBox(height: OmiSpacing.md), action!],
          ],
        ),
      ),
    );
  }
}

/// The toggle on a first-run permission row. The state's colour lives only inside the switch:
/// grey track when unanswered, the accent when allowed, orange (or [deniedColor]) when the reader
/// said no, with a "!" on the thumb so the state does not rely on colour alone.
class OnboardingPermissionToggle extends StatelessWidget {
  const OnboardingPermissionToggle({
    super.key,
    required this.on,
    required this.denied,
    this.busy = false,
    this.deniedColor,
  });

  final bool on;
  final bool denied;
  final bool busy;
  final Color? deniedColor;

  static const double _width = 51;
  static const double _height = 31;
  static const double _thumb = 27;

  @override
  Widget build(BuildContext context) {
    final motion = OmiMotion.of(context);
    final denyColor = deniedColor ?? OmiColors.warning;
    final track = on
        ? OmiColors.accent
        : denied
            ? denyColor
            : OmiColors.surface3;
    // On the accent track the thumb takes the accent's contrast colour (white on black, black on white).
    final thumb = on ? OmiColors.onAccent : const Color(0xFFFFFFFF);
    return AnimatedContainer(
      duration: motion.standard,
      curve: Curves.easeOut,
      width: _width,
      height: _height,
      padding: const EdgeInsets.all(2),
      decoration: BoxDecoration(color: track, borderRadius: OmiRadius.pillAll),
      child: AnimatedAlign(
        duration: motion.standard,
        curve: Curves.easeOut,
        alignment: on ? Alignment.centerRight : Alignment.centerLeft,
        child: Container(
          width: _thumb,
          height: _thumb,
          decoration: BoxDecoration(
            color: thumb,
            shape: BoxShape.circle,
            boxShadow: const [BoxShadow(color: Color(0x26000000), blurRadius: 4, offset: Offset(0, 2))],
          ),
          child: Center(
            child: busy
                ? const SizedBox(width: 14, height: 14, child: OmiSpinner(size: OmiSpinnerSize.small))
                : denied && !on
                    ? Text(
                        '!',
                        style: TextStyle(fontSize: 15, fontWeight: FontWeight.w800, color: denyColor, height: 1),
                      )
                    : null,
          ),
        ),
      ),
    );
  }
}
