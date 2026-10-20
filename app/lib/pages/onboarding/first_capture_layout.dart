import 'package:flutter/material.dart';
import 'package:omi/ui/ui.dart';

/// Scrollable, vertically balanced content with actions in the bottom safe area.
class FirstCaptureLayout extends StatelessWidget {
  const FirstCaptureLayout({super.key, required this.content, required this.actions});
  final List<Widget> content;
  final List<Widget> actions;
  @override
  Widget build(BuildContext context) => SafeArea(
          child: Column(children: [
        Expanded(
            child: LayoutBuilder(
                builder: (context, constraints) => SingleChildScrollView(
                      padding: const EdgeInsets.all(OmiSpacing.lg),
                      child: ConstrainedBox(
                          constraints: BoxConstraints(
                              minHeight: (constraints.maxHeight - OmiSpacing.lg * 2).clamp(0, double.infinity)),
                          child: Column(
                              mainAxisAlignment: MainAxisAlignment.center,
                              crossAxisAlignment: CrossAxisAlignment.stretch,
                              children: content)),
                    ))),
        Padding(
            padding: const EdgeInsets.fromLTRB(OmiSpacing.lg, OmiSpacing.sm, OmiSpacing.lg, OmiSpacing.md),
            child: Column(
                crossAxisAlignment: CrossAxisAlignment.stretch, mainAxisSize: MainAxisSize.min, children: actions)),
      ]));
}
