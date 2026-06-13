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
import 'package:omi/utils/device.dart';

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
              _buildHero(),
              const SizedBox(height: 18),
              Consumer<DeviceProvider>(builder: (context, deviceProvider, _) => _buildDeviceCard(context, deviceProvider)),
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

  Widget _buildHero() {
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
            decoration: BoxDecoration(color: const Color(0xFF22C55E).withValues(alpha: 0.16), borderRadius: BorderRadius.circular(99)),
            child: const Text(
              'Detect & say out loud',
              style: TextStyle(color: Color(0xFF86EFAC), fontSize: 12, fontWeight: FontWeight.w700),
            ),
          ),
          const SizedBox(height: 16),
          const Text(
            'Hear what your glasses see.',
            style: TextStyle(color: Colors.white, fontSize: 30, fontWeight: FontWeight.w800, height: 1.05),
          ),
          const SizedBox(height: 10),
          Text(
            'Omi Glass detects objects locally on this phone and speaks new things out loud.',
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
        ? 'Connected'
        : provider.isConnecting
            ? 'Connecting…'
            : pairedDevice != null
                ? 'Disconnected'
                : 'No glasses connected';
    final subtitle = connectedDevice != null
        ? _deviceSubtitle(connectedDevice, provider.batteryLevel, provider.isCharging)
        : pairedDevice != null
            ? 'Tap to reconnect ${pairedDevice.name.isEmpty ? 'Omi Glass' : pairedDevice.name}.'
            : 'Connect Omi Glass to start local object announcements.';

    return _card(
      child: Column(
        children: [
          _statusRow(
            icon: FontAwesomeIcons.glasses,
            title: 'Omi Glass',
            subtitle: subtitle,
            status: status,
            statusColor: connectedDevice != null ? const Color(0xFF22C55E) : Colors.orangeAccent,
          ),
          const SizedBox(height: 16),
          _fullWidthButton(
            label: hasDevice ? 'Device details' : 'Connect glasses',
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
    final name = device.name.isEmpty ? DeviceUtils.getDeviceName(device.type) : device.name;
    final battery = batteryLevel > 0 ? ' · ${isCharging ? 'Charging ' : ''}$batteryLevel%' : '';
    return '$name$battery · receiving camera frames when available';
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
                  title: 'Object announcements',
                  subtitle: enabled ? _visionStatusText(vision) : 'Off. Detection frames will not be announced.',
                  status: enabled ? 'ON' : 'OFF',
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
                  title: 'All new objects',
                  selected: _currentMode == AnnouncementMode.allObjects,
                  onTap: enabled ? () => _setMode(AnnouncementMode.allObjects) : null,
                ),
              ),
              const SizedBox(width: 10),
              Expanded(
                child: _modeChip(
                  title: 'In my hand',
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
      LocalVisionInferenceStatus.idle => 'Ready. Waiting for Omi Glass images.',
      LocalVisionInferenceStatus.queued => 'New frame queued. Keeping the freshest image only.',
      LocalVisionInferenceStatus.running => 'Detecting objects locally…',
      LocalVisionInferenceStatus.completed => 'Detected ${vision.detectionCount} object${vision.detectionCount == 1 ? '' : 's'}.',
      LocalVisionInferenceStatus.failed => 'Needs attention: ${vision.lastError ?? 'local detector unavailable'}',
    };
  }

  Widget _buildSpeechCard() {
    final voiceEnabled = _prefs.localYoloeVoiceEnabled;
    final announcementService = ObjectAnnouncementService.instance;
    final candidates = LocalVisionService.instance.announcementCandidates;
    final lastPhrase = candidates.isEmpty
        ? 'No new objects to announce yet.'
        : announcementService.formatObjectsMessage(candidates.map((candidate) => candidate.detection.label).toList());

    return _card(
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          Row(
            children: [
              Expanded(
                child: _statusRow(
                  icon: voiceEnabled ? FontAwesomeIcons.volumeHigh : FontAwesomeIcons.volumeXmark,
                  title: 'Speech',
                  subtitle: announcementService.isSpeaking ? 'Speaking now: $lastPhrase' : lastPhrase,
                  status: voiceEnabled ? 'READY' : 'MUTED',
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
                  label: 'Test voice',
                  icon: Icons.play_arrow_rounded,
                  color: const Color(0xFF16A34A),
                  onTap: () => ObjectAnnouncementService.instance.speak('Local object announcements are working.', force: true),
                ),
              ),
              const SizedBox(width: 10),
              Expanded(
                child: _fullWidthButton(
                  label: 'Stop speaking',
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
              const Text('Latest detections', style: TextStyle(color: Colors.white, fontSize: 18, fontWeight: FontWeight.w700)),
              TextButton(
                onPressed: () => Navigator.push(context, MaterialPageRoute(builder: (_) => const ObjectAnnouncementsSettingsPage())),
                child: const Text('Settings', style: TextStyle(color: Color(0xFF86EFAC))),
              ),
            ],
          ),
          const SizedBox(height: 4),
          if (detections.isEmpty)
            Text(
              'No objects detected yet. Connect Omi Glass and keep announcements on.',
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

  Widget _detectionRow(Detection detection) {
    final detail = detection.wouldAnnounce
        ? 'spoken'
        : detection.isHand
            ? 'hand anchor'
            : 'seen';
    return Padding(
      padding: const EdgeInsets.only(top: 10),
      child: Row(
        children: [
          Container(width: 8, height: 8, decoration: const BoxDecoration(color: Color(0xFF22C55E), shape: BoxShape.circle)),
          const SizedBox(width: 10),
          Expanded(
            child: Text(detection.label, style: const TextStyle(color: Colors.white, fontSize: 15, fontWeight: FontWeight.w600)),
          ),
          Text('${(detection.confidence * 100).round()}% · $detail', style: TextStyle(color: Colors.grey.shade400, fontSize: 13)),
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
          Expanded(child: _metric('Frames', '${vision.processedFrameCount}/${vision.receivedFrameCount}')),
          Expanded(child: _metric('Dropped', '${vision.droppedFrameCount}')),
          Expanded(child: _metric('Latency', '${vision.latestLatency.pipelineTotalMs?.toStringAsFixed(0) ?? '—'}ms')),
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
              'Local mode processes images on this phone. Backend image upload and Omi vision LLM calls are skipped for object announcements.',
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
                  Expanded(child: Text(title, style: const TextStyle(color: Colors.white, fontSize: 16, fontWeight: FontWeight.w700))),
                  Container(
                    padding: const EdgeInsets.symmetric(horizontal: 8, vertical: 4),
                    decoration: BoxDecoration(color: statusColor.withValues(alpha: 0.14), borderRadius: BorderRadius.circular(99)),
                    child: Text(status, style: TextStyle(color: statusColor, fontSize: 11, fontWeight: FontWeight.w800)),
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
          child: Center(child: Text(title, style: const TextStyle(color: Colors.white, fontSize: 13, fontWeight: FontWeight.w700))),
        ),
      ),
    );
  }

  Widget _fullWidthButton({required String label, required IconData icon, required Color color, required VoidCallback onTap}) {
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
