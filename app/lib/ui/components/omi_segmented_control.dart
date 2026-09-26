import 'package:flutter/material.dart';

import 'package:omi/ui/components/omi_surface.dart';
import 'package:omi/ui/omi_tokens.dart';

/// One segment of an [OmiSegmentedControl].
class OmiSegment<T> {
  const OmiSegment({required this.value, required this.label});

  final T value;
  final String label;
}

/// The v2 segmented control (Summary / Transcript / Tasks, Monthly / Yearly, Pending / Synced /
/// All): a [OmiColors.surface2] capsule track with a raised thumb under the selected segment.
///
/// Each segment is a 36pt row inside a 44pt touch target, announced as a selected or unselected
/// button. The thumb glides with the v2 spring; under Reduce Motion it jumps.
class OmiSegmentedControl<T> extends StatelessWidget {
  const OmiSegmentedControl({super.key, required this.segments, required this.selected, required this.onChanged});

  final List<OmiSegment<T>> segments;
  final T selected;
  final ValueChanged<T> onChanged;

  static const double _height = 36;

  @override
  Widget build(BuildContext context) {
    final index = segments.indexWhere((s) => s.value == selected);
    final motion = OmiMotion.of(context);
    return SizedBox(
      height: OmiSize.minTap,
      child: Center(
        child: Container(
          height: _height + 4,
          padding: const EdgeInsets.all(2),
          decoration: BoxDecoration(color: OmiColors.surface2, borderRadius: OmiRadius.pillAll),
          child: LayoutBuilder(
            builder: (context, constraints) {
              final width = constraints.maxWidth / segments.length;
              return Stack(
                children: [
                  if (index >= 0)
                    AnimatedPositioned(
                      duration: motion.standard,
                      curve: OmiMotion.springCurve,
                      left: index * width,
                      top: 0,
                      bottom: 0,
                      width: width,
                      child: OmiSurfaceLight(
                        borderRadius: OmiRadius.pillAll,
                        shadows: OmiColors.isLight
                            // Daylight: the iOS white thumb, lifted by a faint shadow.
                            ? const [
                                OmiShadow(color: Color(0x1F14171E), offset: Offset(0, 3), blur: 8),
                                OmiShadow(color: Color(0x0A14171E), offset: Offset(0, 3), blur: 1),
                              ]
                            : const [OmiShadow(color: Color(0x59000000), offset: Offset(0, 2), blur: 6)],
                        topLight: OmiColors.isLight ? null : const Color(0x24FFFFFF),
                        ring: OmiColors.isLight ? const Color(0x0A14171E) : null,
                        child: DecoratedBox(
                          decoration: BoxDecoration(color: OmiColors.segmentThumb, borderRadius: OmiRadius.pillAll),
                        ),
                      ),
                    ),
                  Row(
                    children: [
                      for (final segment in segments)
                        Expanded(
                          child: Semantics(
                            button: true,
                            selected: segment.value == selected,
                            label: segment.label,
                            excludeSemantics: true,
                            onTap: () => _select(segment.value),
                            child: GestureDetector(
                              behavior: HitTestBehavior.opaque,
                              onTap: () => _select(segment.value),
                              child: Center(
                                child: Text(
                                  segment.label,
                                  maxLines: 1,
                                  overflow: TextOverflow.ellipsis,
                                  style: OmiType.subhead.copyWith(
                                    fontSize: 14,
                                    fontWeight: FontWeight.w600,
                                    color: segment.value == selected ? OmiColors.textPrimary : OmiColors.textSecondary,
                                  ),
                                ),
                              ),
                            ),
                          ),
                        ),
                    ],
                  ),
                ],
              );
            },
          ),
        ),
      ),
    );
  }

  void _select(T value) {
    if (value == selected) return;
    OmiHaptics.selection();
    onChanged(value);
  }
}
