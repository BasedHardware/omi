import 'package:flutter/material.dart';
import 'package:flutter/services.dart';
import 'package:font_awesome_flutter/font_awesome_flutter.dart';
import 'package:provider/provider.dart';

import 'package:omi/backend/preferences.dart';
import 'package:omi/backend/schema/bt_device/bt_device.dart';
import 'package:omi/pages/home/device.dart';
import 'package:omi/pages/onboarding/device_selection.dart';
import 'package:omi/pages/settings/object_announcements_settings_page.dart';
import 'package:omi/providers/device_provider.dart';
import 'package:omi/services/local_vision/local_vision_service.dart';
import 'package:omi/services/local_vision/object_announcement_service.dart';
import 'package:omi/utils/l10n_extensions.dart';

class HomeContentPage extends StatefulWidget {
  const HomeContentPage({super.key});

  @override
  State<HomeContentPage> createState() => HomeContentPageState();
}

class HomeContentPageState extends State<HomeContentPage> with AutomaticKeepAliveClientMixin {
  final ScrollController _scrollController = ScrollController();
  final SharedPreferencesUtil _prefs = SharedPreferencesUtil();

  @override
  bool get wantKeepAlive => true;

  void scrollToTop() {
    if (_scrollController.hasClients) {
      _scrollController.animateTo(0.0, duration: const Duration(milliseconds: 500), curve: Curves.easeOutCubic);
    }
  }

  @override
  void dispose() {
    _scrollController.dispose();
    super.dispose();
  }

  Future<void> _setAnnouncementsEnabled(bool value) async {
    HapticFeedback.mediumImpact();
    setState(() => _prefs.localYoloeEnabled = value);
    if (!value) await ObjectAnnouncementService.instance.stop();
  }

  Future<void> _setVoiceEnabled(bool value) async {
    HapticFeedback.lightImpact();
    setState(() => _prefs.localYoloeVoiceEnabled = value);
    if (!value) await ObjectAnnouncementService.instance.stop();
  }

  Future<void> _setMode(AnnouncementMode mode) async {
    HapticFeedback.lightImpact();
    setState(() => _prefs.localYoloeAnnouncementMode = mode.preferenceValue);
    await ObjectAnnouncementService.instance.stop();
  }

  @override
  Widget build(BuildContext context) {
    super.build(context);
    return AnimatedBuilder(
      animation: Listenable.merge([LocalVisionService.instance, ObjectAnnouncementService.instance]),
      builder: (context, _) {
        return RefreshIndicator(
          onRefresh: () async => LocalVisionService.instance.initialize(),
          color: const Color(0xFF22C55E),
          backgroundColor: Colors.white,
          child: ListView(
            controller: _scrollController,
            physics: const AlwaysScrollableScrollPhysics(),
            padding: const EdgeInsets.fromLTRB(20, 8, 20, 32),
            children: [
              _buildHero(context),
              const SizedBox(height: 18),
              Consumer<DeviceProvider>(
                  builder: (context, deviceProvider, _) => _buildDeviceCard(context, deviceProvider)),
              const SizedBox(height: 14),
              _buildAnnouncementControlCard(),
              const SizedBox(height: 14),
              _buildSpeechCard(),
              const SizedBox(height: 14),
              _buildLatestDetectionsCard(),
              const SizedBox(height: 14),
              _buildPrivacyCard(),
            ],
          ),
        );
      },
    );
  }

  Widget _buildHero(BuildContext context) {
    return Container(
      padding: const EdgeInsets.all(22),
      decoration: BoxDecoration(
        borderRadius: BorderRadius.circular(28),
        gradient: const LinearGradient(
          begin: Alignment.topLeft,
          end: Alignment.bottomRight,
          colors: [Color(0xFF12311F), Color(0xFF0F172A)],
        ),
        border: Border.all(color: Colors.white.withValues(alpha: 0.08)),
      ),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          Container(
            padding: const EdgeInsets.symmetric(horizontal: 10, vertical: 6),
            decoration: BoxDecoration(
                color: const Color(0xFF22C55E).withValues(alpha: 0.16), borderRadius: BorderRadius.circular(99)),
            child: Text(
              context.l10n.objectAnnouncementsSettingsTitle,
              style: const TextStyle(color: Color(0xFF86EFAC), fontSize: 12, fontWeight: FontWeight.w700),
            ),
          ),
          const SizedBox(height: 16),
          Text(
            context.l10n.objectAnnouncementsSettingsSubtitle,
            style: const TextStyle(color: Colors.white, fontSize: 30, fontWeight: FontWeight.w800, height: 1.05),
          ),
          const SizedBox(height: 10),
          Text(
            context.l10n.objectAnnouncementsPrivacyCopy,
            style: TextStyle(color: Colors.grey.shade300, fontSize: 15, height: 1.35),
          ),
        ],
      ),
    );
  }

  Widget _buildDeviceCard(BuildContext context, DeviceProvider provider) {
    final connectedDevice = provider.connectedDevice;
    final pairedDevice = provider.pairedDevice;
    final hasDevice = connectedDevice != null || pairedDevice != null;
    final status = connectedDevice != null
        ? context.l10n.connected
        : provider.isConnecting
            ? context.l10n.searching
            : pairedDevice != null
                ? context.l10n.disconnected
                : context.l10n.deviceNotConnected;
    final subtitle = connectedDevice != null
        ? _deviceSubtitle(connectedDevice, provider.batteryLevel, provider.isCharging)
        : pairedDevice != null
            ? context.l10n.objectAnnouncementsReconnectDeviceSubtitle
            : context.l10n.objectAnnouncementsConnectDeviceSubtitle;

    return _card(
      child: Column(
        children: [
          _statusRow(
            icon: FontAwesomeIcons.glasses,
            title: context.l10n.objectAnnouncementsDeviceName,
            subtitle: subtitle,
            status: status,
            statusColor: connectedDevice != null ? const Color(0xFF22C55E) : Colors.orangeAccent,
          ),
          const SizedBox(height: 16),
          _fullWidthButton(
            label: hasDevice ? context.l10n.deviceSettings : context.l10n.connectDevice,
            icon: hasDevice ? Icons.settings_bluetooth_rounded : Icons.bluetooth_searching_rounded,
            color: const Color(0xFF27272A),
            onTap: () {
              HapticFeedback.mediumImpact();
              Navigator.push(
                context,
                MaterialPageRoute(builder: (_) => hasDevice ? const ConnectedDevice() : const DeviceSelectionPage()),
              );
            },
          ),
        ],
      ),
    );
  }

  String _deviceSubtitle(BtDevice device, int batteryLevel, bool isCharging) {
    final name = device.name.isEmpty ? context.l10n.objectAnnouncementsDeviceName : device.name;
    final battery = batteryLevel > 0 ? ' · ${isCharging ? '${context.l10n.charging} ' : ''}$batteryLevel%' : '';
    return '$name$battery · ${context.l10n.objectAnnouncementsDeviceFrameSubtitle}';
  }

  Widget _buildAnnouncementControlCard() {
    final enabled = _prefs.localYoloeEnabled;
    final vision = LocalVisionService.instance;
    return _card(
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          Row(
            children: [
              Expanded(
                child: _statusRow(
                  icon: FontAwesomeIcons.eye,
                  title: context.l10n.objectAnnouncementsSettingsTitle,
                  subtitle: enabled ? _visionStatusText(vision) : context.l10n.objectAnnouncementsOffSubtitle,
                  status: enabled ? context.l10n.on.toUpperCase() : context.l10n.off.toUpperCase(),
                  statusColor: enabled ? const Color(0xFF22C55E) : Colors.grey,
                ),
              ),
              Switch(value: enabled, onChanged: _setAnnouncementsEnabled, activeThumbColor: const Color(0xFF22C55E)),
            ],
          ),
          const SizedBox(height: 16),
          Row(
            children: [
              Expanded(
                child: _modeChip(
                  title: context.l10n.objectAnnouncementsAllObjectsModeTitle,
                  selected: _currentMode == AnnouncementMode.allObjects,
                  onTap: enabled ? () => _setMode(AnnouncementMode.allObjects) : null,
                ),
              ),
              const SizedBox(width: 10),
              Expanded(
                child: _modeChip(
                  title: context.l10n.objectAnnouncementsHeldObjectsModeTitle,
                  selected: _currentMode == AnnouncementMode.heldObjectsOnly,
                  onTap: enabled ? () => _setMode(AnnouncementMode.heldObjectsOnly) : null,
                ),
              ),
            ],
          ),
        ],
      ),
    );
  }

  AnnouncementMode get _currentMode => AnnouncementModeSettings.fromPreference(_prefs.localYoloeAnnouncementMode);

  String _visionStatusText(LocalVisionService vision) {
    return switch (vision.status) {
      LocalVisionInferenceStatus.idle => context.l10n.objectAnnouncementsMainToggleSubtitle,
      LocalVisionInferenceStatus.queued => context.l10n.objectAnnouncementsFrameQueued,
      LocalVisionInferenceStatus.running => context.l10n.objectAnnouncementsDetectingLocally,
      LocalVisionInferenceStatus.completed => context.l10n.objectAnnouncementsDetectionCount(vision.detectionCount),
      LocalVisionInferenceStatus.failed => '${context.l10n.somethingWentWrong}: ${vision.lastError ?? ''}',
    };
  }

  Widget _buildSpeechCard() {
    final voiceEnabled = _prefs.localYoloeVoiceEnabled;
    final announcementService = ObjectAnnouncementService.instance;
    final candidates = LocalVisionService.instance.announcementCandidates;
    final lastSpokenText = announcementService.lastSpokenText;
    final candidatePhrase = candidates.isEmpty
        ? null
        : announcementService.formatObjectsMessage(candidates.map((candidate) => candidate.detection.label).toList());
    final phrase = lastSpokenText ?? candidatePhrase ?? context.l10n.objectAnnouncementsNoNewObjects;

    return _card(
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          Row(
            children: [
              Expanded(
                child: _statusRow(
                  icon: voiceEnabled ? FontAwesomeIcons.volumeHigh : FontAwesomeIcons.volumeXmark,
                  title: context.l10n.objectAnnouncementsVoiceTitle,
                  subtitle:
                      announcementService.isSpeaking ? context.l10n.objectAnnouncementsSpeakingNow(phrase) : phrase,
                  status: voiceEnabled ? context.l10n.on.toUpperCase() : context.l10n.muted.toUpperCase(),
                  statusColor: voiceEnabled ? const Color(0xFF22C55E) : Colors.grey,
                ),
              ),
              Switch(value: voiceEnabled, onChanged: _setVoiceEnabled, activeThumbColor: const Color(0xFF22C55E)),
            ],
          ),
          const SizedBox(height: 16),
          Row(
            children: [
              Expanded(
                child: _fullWidthButton(
                  label: context.l10n.objectAnnouncementsTestVoiceButton,
                  icon: Icons.play_arrow_rounded,
                  color: const Color(0xFF16A34A),
                  onTap: () => ObjectAnnouncementService.instance.speak(
                    context.l10n.objectAnnouncementsTestVoiceMessage,
                    force: true,
                  ),
                ),
              ),
              const SizedBox(width: 10),
              Expanded(
                child: _fullWidthButton(
                  label: context.l10n.stop,
                  icon: Icons.stop_rounded,
                  color: const Color(0xFF27272A),
                  onTap: ObjectAnnouncementService.instance.stop,
                ),
              ),
            ],
          ),
        ],
      ),
    );
  }

  Widget _buildLatestDetectionsCard() {
    final vision = LocalVisionService.instance;
    final detections = vision.detections.take(5).toList();

    return _card(
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          Row(
            mainAxisAlignment: MainAxisAlignment.spaceBetween,
            children: [
              Text(
                context.l10n.objectAnnouncementsLatestDetectionsTitle,
                style: const TextStyle(color: Colors.white, fontSize: 18, fontWeight: FontWeight.w700),
              ),
              TextButton(
                onPressed: () =>
                    Navigator.push(context, MaterialPageRoute(builder: (_) => const ObjectAnnouncementsSettingsPage())),
                child: Text(context.l10n.settings, style: const TextStyle(color: Color(0xFF86EFAC))),
              ),
            ],
          ),
          const SizedBox(height: 4),
          _buildLiveVisionPreview(vision),
          const SizedBox(height: 14),
          if (detections.isEmpty)
            Text(
              context.l10n.objectAnnouncementsNoDetections,
              style: TextStyle(color: Colors.grey.shade400, fontSize: 14, height: 1.35),
            )
          else
            ...detections.map(_detectionRow),
          const SizedBox(height: 14),
          _metricStrip(vision),
        ],
      ),
    );
  }

  Widget _buildLiveVisionPreview(LocalVisionService vision) {
    final frameBytes = vision.latestFrameJpegBytes;
    final detections = vision.detections;
    return ClipRRect(
      borderRadius: BorderRadius.circular(16),
      child: Container(
        color: const Color(0xFF111113),
        child: AspectRatio(
          aspectRatio: 4 / 3,
          child: frameBytes == null
              ? Center(
                  child: Text(
                    context.l10n.objectAnnouncementsNoDetections,
                    style: TextStyle(color: Colors.grey.shade500, fontSize: 13),
                  ),
                )
              : Stack(
                  fit: StackFit.expand,
                  children: [
                    Image.memory(
                      frameBytes,
                      fit: BoxFit.fill,
                      gaplessPlayback: true,
                    ),
                    CustomPaint(painter: _LocalVisionOverlayPainter(detections)),
                    Positioned(
                      left: 10,
                      top: 10,
                      child: Container(
                        padding: const EdgeInsets.symmetric(horizontal: 8, vertical: 5),
                        decoration: BoxDecoration(
                          color: Colors.black.withValues(alpha: 0.58),
                          borderRadius: BorderRadius.circular(99),
                        ),
                        child: Text(
                          '${vision.detectionCount} · ${vision.status.name}',
                          style: const TextStyle(color: Colors.white, fontSize: 11, fontWeight: FontWeight.w800),
                        ),
                      ),
                    ),
                  ],
                ),
        ),
      ),
    );
  }

  Widget _detectionRow(Detection detection) {
    final detail = detection.wouldAnnounce
        ? context.l10n.objectAnnouncementsSpokenStatus
        : detection.isHand
            ? context.l10n.objectAnnouncementsHandAnchorStatus
            : context.l10n.objectAnnouncementsSeenStatus;
    return Padding(
      padding: const EdgeInsets.only(top: 10),
      child: Row(
        children: [
          Container(
              width: 8, height: 8, decoration: const BoxDecoration(color: Color(0xFF22C55E), shape: BoxShape.circle)),
          const SizedBox(width: 10),
          Expanded(
            child: Text(detection.label,
                style: const TextStyle(color: Colors.white, fontSize: 15, fontWeight: FontWeight.w600)),
          ),
          Text('${(detection.confidence * 100).round()}% · $detail',
              style: TextStyle(color: Colors.grey.shade400, fontSize: 13)),
        ],
      ),
    );
  }

  Widget _metricStrip(LocalVisionService vision) {
    return Container(
      padding: const EdgeInsets.all(12),
      decoration: BoxDecoration(color: const Color(0xFF111113), borderRadius: BorderRadius.circular(14)),
      child: Row(
        children: [
          Expanded(
            child: _metric(
              context.l10n.objectAnnouncementsFramesMetric,
              '${vision.processedFrameCount}/${vision.receivedFrameCount}',
            ),
          ),
          Expanded(child: _metric(context.l10n.objectAnnouncementsDroppedMetric, '${vision.droppedFrameCount}')),
          Expanded(
            child: _metric(
              context.l10n.objectAnnouncementsLatencyMetric,
              '${vision.latestLatency.pipelineTotalMs?.toStringAsFixed(0) ?? '—'}ms',
            ),
          ),
        ],
      ),
    );
  }

  Widget _metric(String label, String value) {
    return Column(
      crossAxisAlignment: CrossAxisAlignment.start,
      children: [
        Text(value, style: const TextStyle(color: Colors.white, fontSize: 15, fontWeight: FontWeight.w700)),
        const SizedBox(height: 2),
        Text(label, style: TextStyle(color: Colors.grey.shade500, fontSize: 11)),
      ],
    );
  }

  Widget _buildPrivacyCard() {
    return Container(
      padding: const EdgeInsets.all(16),
      decoration: BoxDecoration(
        color: const Color(0xFF122019),
        borderRadius: BorderRadius.circular(20),
        border: Border.all(color: const Color(0xFF22C55E).withValues(alpha: 0.2)),
      ),
      child: Row(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          const FaIcon(FontAwesomeIcons.shieldHalved, color: Color(0xFF22C55E), size: 18),
          const SizedBox(width: 12),
          Expanded(
            child: Text(
              context.l10n.objectAnnouncementsPrivacyCopy,
              style: TextStyle(color: Colors.grey.shade200, fontSize: 13, height: 1.35),
            ),
          ),
        ],
      ),
    );
  }

  Widget _card({required Widget child}) {
    return Container(
      padding: const EdgeInsets.all(16),
      decoration: BoxDecoration(
        color: const Color(0xFF1C1C1E),
        borderRadius: BorderRadius.circular(22),
        border: Border.all(color: Colors.white.withValues(alpha: 0.06)),
      ),
      child: child,
    );
  }

  Widget _statusRow({
    required FaIconData icon,
    required String title,
    required String subtitle,
    required String status,
    required Color statusColor,
  }) {
    return Row(
      crossAxisAlignment: CrossAxisAlignment.start,
      children: [
        Container(
          width: 42,
          height: 42,
          decoration: BoxDecoration(color: const Color(0xFF2A2A2E), borderRadius: BorderRadius.circular(12)),
          child: Center(child: FaIcon(icon, color: Colors.grey.shade300, size: 17)),
        ),
        const SizedBox(width: 12),
        Expanded(
          child: Column(
            crossAxisAlignment: CrossAxisAlignment.start,
            children: [
              Row(
                children: [
                  Expanded(
                      child: Text(title,
                          style: const TextStyle(color: Colors.white, fontSize: 16, fontWeight: FontWeight.w700))),
                  Container(
                    padding: const EdgeInsets.symmetric(horizontal: 8, vertical: 4),
                    decoration: BoxDecoration(
                        color: statusColor.withValues(alpha: 0.14), borderRadius: BorderRadius.circular(99)),
                    child:
                        Text(status, style: TextStyle(color: statusColor, fontSize: 11, fontWeight: FontWeight.w800)),
                  ),
                ],
              ),
              const SizedBox(height: 4),
              Text(subtitle, style: TextStyle(color: Colors.grey.shade400, fontSize: 13, height: 1.3)),
            ],
          ),
        ),
      ],
    );
  }

  Widget _modeChip({required String title, required bool selected, required VoidCallback? onTap}) {
    return GestureDetector(
      onTap: onTap,
      child: Opacity(
        opacity: onTap == null ? 0.45 : 1,
        child: Container(
          padding: const EdgeInsets.symmetric(horizontal: 12, vertical: 12),
          decoration: BoxDecoration(
            color: selected ? const Color(0xFF22C55E).withValues(alpha: 0.16) : const Color(0xFF111113),
            borderRadius: BorderRadius.circular(14),
            border: Border.all(color: selected ? const Color(0xFF22C55E) : const Color(0xFF2A2A2E)),
          ),
          child: Center(
              child:
                  Text(title, style: const TextStyle(color: Colors.white, fontSize: 13, fontWeight: FontWeight.w700))),
        ),
      ),
    );
  }

  Widget _fullWidthButton(
      {required String label, required IconData icon, required Color color, required VoidCallback onTap}) {
    return GestureDetector(
      onTap: onTap,
      child: Container(
        padding: const EdgeInsets.symmetric(vertical: 13),
        decoration: BoxDecoration(color: color, borderRadius: BorderRadius.circular(14)),
        child: Row(
          mainAxisAlignment: MainAxisAlignment.center,
          children: [
            Icon(icon, color: Colors.white, size: 18),
            const SizedBox(width: 8),
            Text(label, style: const TextStyle(color: Colors.white, fontSize: 14, fontWeight: FontWeight.w800)),
          ],
        ),
      ),
    );
  }
}

class _LocalVisionOverlayPainter extends CustomPainter {
  _LocalVisionOverlayPainter(this.detections);

  final List<Detection> detections;

  @override
  void paint(Canvas canvas, Size size) {
    final boxPaint = Paint()
      ..color = const Color(0xFF22C55E)
      ..style = PaintingStyle.stroke
      ..strokeWidth = 2.2;
    final fillPaint = Paint()
      ..color = const Color(0xFF22C55E).withValues(alpha: 0.10)
      ..style = PaintingStyle.fill;

    for (final detection in detections.take(12)) {
      final rect = Rect.fromLTWH(
        detection.box.left * size.width,
        detection.box.top * size.height,
        detection.box.width * size.width,
        detection.box.height * size.height,
      );
      if (rect.width <= 0 || rect.height <= 0) continue;

      canvas.drawRect(rect, fillPaint);
      canvas.drawRect(rect, boxPaint);

      final label = '${detection.label} ${(detection.confidence * 100).round()}%';
      final textPainter = TextPainter(
        text: TextSpan(
          text: label,
          style: const TextStyle(color: Colors.white, fontSize: 11, fontWeight: FontWeight.w800),
        ),
        maxLines: 1,
        textDirection: TextDirection.ltr,
      )..layout(maxWidth: size.width - 16);

      final labelWidth = textPainter.width + 10;
      final labelHeight = textPainter.height + 6;
      final labelLeft = rect.left.clamp(0.0, (size.width - labelWidth).clamp(0.0, size.width));
      final labelTop = (rect.top - labelHeight).clamp(0.0, (size.height - labelHeight).clamp(0.0, size.height));
      final labelRect = RRect.fromRectAndRadius(
        Rect.fromLTWH(labelLeft, labelTop, labelWidth, labelHeight),
        const Radius.circular(6),
      );
      canvas.drawRRect(labelRect, Paint()..color = Colors.black.withValues(alpha: 0.72));
      textPainter.paint(canvas, Offset(labelLeft + 5, labelTop + 3));
    }
  }

  @override
  bool shouldRepaint(covariant _LocalVisionOverlayPainter oldDelegate) {
    return oldDelegate.detections != detections;
  }
}
