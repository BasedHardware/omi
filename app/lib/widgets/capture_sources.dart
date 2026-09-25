import 'package:flutter/material.dart';

import 'package:omi/utils/l10n_extensions.dart';

/// The device vocabulary shared by the conversation list and the detail
/// header: one icon and one name per capture surface (wire source string).
abstract final class CaptureSources {
  static IconData icon(String? source) {
    switch (source) {
      case 'desktop':
        return Icons.desktop_mac_outlined;
      case 'omi':
      case 'friend':
      case 'friend_com':
      case 'limitless':
      case 'bee':
      case 'plaud':
      case 'fieldy':
        return Icons.sensors;
      case 'phone':
        return Icons.phone_iphone;
      case 'apple_watch':
        return Icons.watch_outlined;
      case 'openglass':
      case 'rayban_meta':
        return Icons.camera_alt_outlined;
      default:
        return Icons.mic_none;
    }
  }

  static String label(BuildContext context, String? source) {
    switch (source) {
      case 'desktop':
        return context.l10n.captureSourceDesktop;
      // The wearable is "Pendant" wherever a capture source is named (design ruling 2026-09-24),
      // never "Omi", which is the app.
      case 'omi':
        return context.l10n.captureSourcePendant;
      case 'phone':
        return context.l10n.phone;
      // Product and brand names are not translated.
      case 'apple_watch':
        return 'Apple Watch';
      case 'limitless':
        return 'Limitless';
      case 'bee':
        return 'Bee';
      case 'plaud':
        return 'Plaud';
      case 'fieldy':
        return 'Fieldy';
      case 'openglass':
        return 'OmiGlass';
      case 'rayban_meta':
        return 'Ray-Ban Meta';
      case 'friend':
      case 'friend_com':
        return 'Friend';
      default:
        return context.l10n.device;
    }
  }
}

/// The devices that recorded one event, as a row of small icons (list rows).
class CaptureSourceIcons extends StatelessWidget {
  const CaptureSourceIcons({super.key, required this.sources, this.color = const Color(0xFF9A9BA1), this.size = 14});

  final List<String> sources;
  final Color color;
  final double size;

  @override
  Widget build(BuildContext context) {
    final names = sources.map((source) => CaptureSources.label(context, source)).join(', ');
    return Semantics(
      label: context.l10n.captureRecordedBy(names),
      excludeSemantics: true,
      child: Row(
        mainAxisSize: MainAxisSize.min,
        children: [
          for (final (index, source) in sources.indexed) ...[
            if (index > 0) const SizedBox(width: 3),
            Icon(CaptureSources.icon(source), size: size, color: color),
          ],
        ],
      ),
    );
  }
}

/// The header's device stack: one small overlapping circle per recording, in
/// start order, at most [limit].
class CaptureSourceStack extends StatelessWidget {
  const CaptureSourceStack({super.key, required this.sources, this.limit = 3});

  final List<String?> sources;
  final int limit;

  static const double _diameter = 22;
  static const double _overlap = 7;

  @override
  Widget build(BuildContext context) {
    final shown = sources.take(limit).toList();
    return SizedBox(
      width: _diameter + (shown.length - 1) * (_diameter - _overlap),
      height: _diameter,
      child: Stack(
        children: [
          for (final (index, source) in shown.indexed.toList().reversed)
            Positioned(
              left: index * (_diameter - _overlap),
              child: Container(
                width: _diameter,
                height: _diameter,
                decoration: BoxDecoration(
                  color: const Color(0xFF2A2A31),
                  shape: BoxShape.circle,
                  border: Border.all(color: const Color(0xFF1F1F25), width: 1.5),
                ),
                child: Icon(CaptureSources.icon(source), size: 12, color: Colors.white),
              ),
            ),
        ],
      ),
    );
  }
}
