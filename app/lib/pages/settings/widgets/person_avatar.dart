import 'package:flutter/material.dart';

import 'package:omi/backend/schema/person.dart';
import 'package:omi/ui/ui.dart';

/// A person's initials on a muted speaker colour, stable for their id (list order and deletes do
/// not recolour anyone). A small badge says whether Omi knows their voice: green when it is
/// ready, amber while a saved sample is still processing, none when it has not been learned.
///
/// Decorative for accessibility: the row or header that holds it names the person and the voice
/// status.
class PersonAvatar extends StatelessWidget {
  const PersonAvatar({super.key, required this.person, this.size = 44, this.ring});

  final Person person;
  final double size;

  /// The surface behind the avatar, drawn as a ring around the badge so it reads as cut out.
  final Color? ring;

  static String initials(String name) {
    final words = name.trim().split(RegExp(r'\s+')).where((w) => w.isNotEmpty).toList();
    if (words.isEmpty) return '?';
    final first = words.first.characters.first;
    final last = words.length > 1 ? words.last.characters.first : '';
    return (first + last).toUpperCase();
  }

  static Color colorFor(String id) {
    final hash = id.codeUnits.fold<int>(0, (h, c) => (h * 31 + c) & 0x7fffffff);
    return speakerColors[hash % speakerColors.length];
  }

  @override
  Widget build(BuildContext context) {
    final badge = switch (person.voiceReadiness) {
      'ready' => OmiColors.success,
      'saved_sample_awaiting_embedding' => OmiColors.warning,
      _ => null,
    };
    final badgeSize = size * 0.34;
    return ExcludeSemantics(
      child: SizedBox.square(
        dimension: size,
        child: Stack(
          clipBehavior: Clip.none,
          children: [
            Container(
              width: size,
              height: size,
              alignment: Alignment.center,
              decoration: BoxDecoration(color: colorFor(person.id), shape: BoxShape.circle),
              // Speaker colours are dark in both appearances, so the initials are always light.
              child: Text(
                initials(person.name),
                style: OmiType.headline.copyWith(fontSize: size * 0.36, color: OmiPalette.dark.textPrimary),
                maxLines: 1,
                textScaler: TextScaler.noScaling,
              ),
            ),
            if (badge != null)
              Positioned(
                right: -1,
                bottom: -1,
                child: Container(
                  width: badgeSize,
                  height: badgeSize,
                  decoration: BoxDecoration(
                    color: badge,
                    shape: BoxShape.circle,
                    border: Border.all(color: ring ?? OmiColors.surface1, width: 2),
                  ),
                  child: Icon(Icons.graphic_eq, size: badgeSize * 0.6, color: OmiPalette.dark.textPrimary),
                ),
              ),
          ],
        ),
      ),
    );
  }
}
