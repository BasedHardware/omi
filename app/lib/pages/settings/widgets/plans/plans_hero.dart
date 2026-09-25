import 'package:flutter/material.dart';

import 'package:omi/gen/assets.gen.dart';
import 'package:omi/ui/omi_tokens.dart';

/// The decorative header of the plans sheet: an audio waveform scrolling into the Omi device on
/// the left and notes scrolling out on the right. Purely decorative, so it is hidden from screen
/// readers.
class PlansHero extends StatelessWidget {
  const PlansHero({super.key, required this.waveController, required this.notesController});

  final AnimationController waveController;
  final AnimationController notesController;

  static const _waveHeights = [
    20.0, 32.0, 45.0, 26.0, 52.0, 39.0, 32.0, 45.0, 28.0, 36.0, 41.0, 24.0, //
    48.0, 37.0, 30.0, 43.0, 22.0, 34.0, 47.0, 29.0, 50.0, 38.0, 33.0, 44.0,
  ];

  @override
  Widget build(BuildContext context) {
    return ExcludeSemantics(
      child: SizedBox(
        height: 150,
        width: double.infinity,
        child: Stack(
          alignment: Alignment.topCenter,
          children: [
            Row(
              children: [
                Expanded(
                  child: _ScrollingStrip(
                    controller: waveController,
                    totalWidth: 420,
                    // The trailing copy repeats a shorter cycle, as the original artwork did.
                    leading: _wave(_waveHeights),
                    trailing: _wave(_waveHeights.sublist(0, 8)),
                  ),
                ),
                Expanded(
                  child: _ScrollingStrip(
                    controller: notesController,
                    totalWidth: 440,
                    leading: _notes(),
                    trailing: _notes(),
                  ),
                ),
              ],
            ),
            Positioned(
              top: 5,
              child: Container(
                width: 120,
                height: 120,
                decoration: BoxDecoration(
                  shape: BoxShape.circle,
                  boxShadow: [BoxShadow(color: Colors.blue.withValues(alpha: 0.4), blurRadius: 20, spreadRadius: 3)],
                ),
                child: ClipOval(child: Image.asset(Assets.images.omiWithoutRope.path, fit: BoxFit.cover)),
              ),
            ),
          ],
        ),
      ),
    );
  }

  static Widget _wave(List<double> heights) {
    return Row(
      children: List.generate(60, (index) {
        return Container(
          width: 4,
          height: heights[index % heights.length],
          margin: const EdgeInsets.symmetric(horizontal: 1.5),
          decoration: BoxDecoration(color: Colors.red.withValues(alpha: 0.7), borderRadius: OmiRadius.pillAll),
        );
      }),
    );
  }

  static Widget _notes() {
    return Row(
      children: List.generate(8, (index) {
        return Container(
          width: 45,
          height: 55,
          margin: const EdgeInsets.symmetric(horizontal: 5),
          decoration: BoxDecoration(
            color: Colors.white.withValues(alpha: 0.95),
            borderRadius: OmiRadius.smAll,
            boxShadow: [
              BoxShadow(color: Colors.black.withValues(alpha: 0.15), blurRadius: 4, offset: const Offset(0, 2)),
            ],
          ),
          child: Padding(
            padding: const EdgeInsets.all(6),
            child: Column(
              crossAxisAlignment: CrossAxisAlignment.start,
              children: [
                Container(
                  width: 26,
                  height: 3,
                  decoration: const BoxDecoration(color: Colors.black, borderRadius: OmiRadius.pillAll),
                ),
                const SizedBox(height: 4),
                ...List.generate(
                  5,
                  (i) => Container(
                    width: i == 4 ? 24 : 35, // Last line shorter
                    height: 2,
                    margin: const EdgeInsets.symmetric(vertical: 2),
                    decoration: BoxDecoration(color: Colors.grey[350], borderRadius: OmiRadius.pillAll),
                  ),
                ),
              ],
            ),
          ),
        );
      }),
    );
  }
}

/// Two copies of [leading]/[trailing] scrolling left to right in a loop.
class _ScrollingStrip extends StatelessWidget {
  const _ScrollingStrip({
    required this.controller,
    required this.totalWidth,
    required this.leading,
    required this.trailing,
  });

  final AnimationController controller;
  final double totalWidth;
  final Widget leading;
  final Widget trailing;

  @override
  Widget build(BuildContext context) {
    return ClipRect(
      child: SizedBox(
        height: 120,
        child: AnimatedBuilder(
          animation: controller,
          builder: (context, child) {
            final scrollOffset = (controller.value * totalWidth) % totalWidth;
            return Stack(
              children: [
                Positioned(left: -totalWidth + scrollOffset, top: 0, bottom: 0, child: leading),
                Positioned(left: scrollOffset, top: 0, bottom: 0, child: trailing),
              ],
            );
          },
        ),
      ),
    );
  }
}
