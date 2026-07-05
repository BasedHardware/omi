import 'package:flutter/material.dart';
import 'package:flutter/services.dart';

import 'package:provider/provider.dart';

import 'package:omi/backend/preferences.dart';
import 'package:omi/backend/schema/bt_device/bt_device.dart';
import 'package:omi/providers/capture_provider.dart';
import 'package:omi/services/capture/capture_controller.dart';
import 'package:omi/utils/l10n_extensions.dart';

class CaptureModeChip extends StatelessWidget {
  final DeviceType deviceType;

  const CaptureModeChip({super.key, required this.deviceType});

  static bool supportsDevice(DeviceType? type) => CaptureController.supportsTranscribeLater(type);

  @override
  Widget build(BuildContext context) {
    if (!supportsDevice(deviceType)) return const SizedBox.shrink();
    return Consumer<CaptureProvider>(
      builder: (context, provider, _) {
        final later = SharedPreferencesUtil().batchModeEnabled;
        return GestureDetector(
          behavior: HitTestBehavior.opaque,
          onTap: () {
            HapticFeedback.lightImpact();
            _showModeSheet(context, provider);
          },
          child: Container(
            height: 36,
            padding: const EdgeInsets.fromLTRB(10, 0, 6, 0),
            decoration: BoxDecoration(color: const Color(0xFF1F1F25), borderRadius: BorderRadius.circular(18)),
            child: Row(
              mainAxisSize: MainAxisSize.min,
              children: [
                Icon(later ? Icons.schedule_rounded : Icons.graphic_eq_rounded, size: 14, color: Colors.white),
                const SizedBox(width: 6),
                Text(
                  later ? context.l10n.captureModeLater : context.l10n.live,
                  style: const TextStyle(color: Colors.white, fontSize: 12, fontWeight: FontWeight.w600),
                ),
                Icon(Icons.keyboard_arrow_down_rounded, size: 16, color: Colors.grey.shade400),
              ],
            ),
          ),
        );
      },
    );
  }

  void _showModeSheet(BuildContext context, CaptureProvider provider) {
    showModalBottomSheet(
      context: context,
      backgroundColor: Colors.transparent,
      isScrollControlled: true,
      builder: (_) => _CaptureModeSheet(provider: provider),
    );
  }
}

class _CaptureModeSheet extends StatelessWidget {
  final CaptureProvider provider;

  const _CaptureModeSheet({required this.provider});

  @override
  Widget build(BuildContext context) {
    final later = SharedPreferencesUtil().batchModeEnabled;
    return Container(
      padding: EdgeInsets.fromLTRB(16, 12, 16, MediaQuery.of(context).padding.bottom + 16),
      decoration: const BoxDecoration(
        color: Color(0xFF1F1F25),
        borderRadius: BorderRadius.vertical(top: Radius.circular(24)),
      ),
      child: Column(
        mainAxisSize: MainAxisSize.min,
        crossAxisAlignment: CrossAxisAlignment.stretch,
        children: [
          Center(
            child: Container(
              width: 36,
              height: 4,
              decoration: BoxDecoration(color: Colors.white24, borderRadius: BorderRadius.circular(2)),
            ),
          ),
          const SizedBox(height: 18),
          Padding(
            padding: const EdgeInsets.only(left: 4, bottom: 14),
            child: Text(
              context.l10n.recordingMode,
              style: const TextStyle(color: Colors.white, fontSize: 18, fontWeight: FontWeight.w600),
            ),
          ),
          _ModeOption(
            icon: Icons.graphic_eq_rounded,
            title: context.l10n.live,
            subtitle: context.l10n.captureModeLiveDescription,
            selected: !later,
            onTap: () => _select(context, false),
          ),
          const SizedBox(height: 10),
          _ModeOption(
            icon: Icons.schedule_rounded,
            title: context.l10n.transcribeLaterTitle,
            subtitle: context.l10n.captureModeLaterDescription,
            selected: later,
            onTap: () => _select(context, true),
          ),
        ],
      ),
    );
  }

  Future<void> _select(BuildContext context, bool batch) async {
    HapticFeedback.lightImpact();
    Navigator.pop(context);
    if (SharedPreferencesUtil().batchModeEnabled == batch) return;
    await provider.setBatchMode(batch);
  }
}

class _ModeOption extends StatelessWidget {
  final IconData icon;
  final String title;
  final String subtitle;
  final bool selected;
  final VoidCallback onTap;

  const _ModeOption({
    required this.icon,
    required this.title,
    required this.subtitle,
    required this.selected,
    required this.onTap,
  });

  @override
  Widget build(BuildContext context) {
    return GestureDetector(
      onTap: onTap,
      child: Container(
        padding: const EdgeInsets.symmetric(horizontal: 14, vertical: 14),
        decoration: BoxDecoration(
          color: const Color(0xFF2A2A33),
          borderRadius: BorderRadius.circular(16),
          border: Border.all(
            color: selected ? Colors.white.withValues(alpha: 0.55) : Colors.transparent,
            width: 1.5,
          ),
        ),
        child: Row(
          children: [
            Container(
              width: 40,
              height: 40,
              decoration: BoxDecoration(color: const Color(0xFF35343B), borderRadius: BorderRadius.circular(12)),
              child: Icon(icon, color: Colors.white, size: 18),
            ),
            const SizedBox(width: 14),
            Expanded(
              child: Column(
                mainAxisSize: MainAxisSize.min,
                crossAxisAlignment: CrossAxisAlignment.start,
                children: [
                  Text(
                    title,
                    style: const TextStyle(color: Colors.white, fontSize: 15, fontWeight: FontWeight.w600),
                  ),
                  const SizedBox(height: 3),
                  Text(subtitle, style: TextStyle(color: Colors.grey[400], fontSize: 12.5, height: 1.3)),
                ],
              ),
            ),
            const SizedBox(width: 10),
            Container(
              width: 22,
              height: 22,
              decoration: BoxDecoration(
                shape: BoxShape.circle,
                color: selected ? Colors.white : Colors.transparent,
                border: Border.all(color: selected ? Colors.white : Colors.grey.shade600, width: 2),
              ),
              child: selected ? const Icon(Icons.check, size: 14, color: Color(0xFF1F1F25)) : null,
            ),
          ],
        ),
      ),
    );
  }
}
