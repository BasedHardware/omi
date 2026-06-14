import 'package:flutter/material.dart';
import 'package:font_awesome_flutter/font_awesome_flutter.dart';

import 'package:omi/backend/preferences.dart';
import 'package:omi/services/local_vision/local_vision_service.dart';
import 'package:omi/services/local_vision/object_announcement_service.dart';
import 'package:omi/utils/l10n_extensions.dart';

class ObjectAnnouncementsSettingsPage extends StatefulWidget {
  const ObjectAnnouncementsSettingsPage({super.key, this.showBackButton = true});

  final bool showBackButton;

  @override
  State<ObjectAnnouncementsSettingsPage> createState() => _ObjectAnnouncementsSettingsPageState();
}

class _ObjectAnnouncementsSettingsPageState extends State<ObjectAnnouncementsSettingsPage> {
  final _prefs = SharedPreferencesUtil();

  late bool _enabled;
  late bool _voiceEnabled;
  late bool _interruptSpeech;
  late bool _adaptiveThrottlingEnabled;
  late AnnouncementMode _mode;
  late LocalVisionDetectorImplementation _detectorImplementation;
  late double _speechRate;
  late double _announcementCooldown;
  late double _confidenceThreshold;
  late double _handIouThreshold;
  late int _maxObjectsPerAnnouncement;

  @override
  void initState() {
    super.initState();
    _enabled = _prefs.localYoloeEnabled;
    _voiceEnabled = _prefs.localYoloeVoiceEnabled;
    _interruptSpeech = _prefs.localYoloeInterruptSpeech;
    _adaptiveThrottlingEnabled = _prefs.localYoloeAdaptiveThrottlingEnabled;
    _mode = AnnouncementModeSettings.fromPreference(_prefs.localYoloeAnnouncementMode);
    _detectorImplementation = LocalVisionDetectorImplementationSettings.fromPreference(
      _prefs.localYoloeDetectorImplementation,
    );
    _speechRate = _prefs.localYoloeSpeechRate;
    _announcementCooldown = _prefs.localYoloeMinSecondsBetweenAnnouncements;
    _confidenceThreshold = _prefs.localYoloeConfidenceThreshold;
    _handIouThreshold = _prefs.localYoloeHandObjectIouThreshold;
    _maxObjectsPerAnnouncement = _prefs.localYoloeMaxObjectsPerAnnouncement;
  }

  Widget _section({required List<Widget> children}) {
    return Container(
      decoration: BoxDecoration(color: const Color(0xFF1C1C1E), borderRadius: BorderRadius.circular(16)),
      child: Column(children: children),
    );
  }

  Widget _row({
    required String title,
    required String subtitle,
    required FaIconData icon,
    required Widget trailing,
    bool enabled = true,
  }) {
    return Opacity(
      opacity: enabled ? 1 : 0.48,
      child: Padding(
        padding: const EdgeInsets.all(16),
        child: Row(
          children: [
            Container(
              width: 40,
              height: 40,
              decoration: BoxDecoration(color: const Color(0xFF2A2A2E), borderRadius: BorderRadius.circular(10)),
              child: Center(child: FaIcon(icon, color: Colors.grey.shade400, size: 16)),
            ),
            const SizedBox(width: 14),
            Expanded(
              child: Column(
                crossAxisAlignment: CrossAxisAlignment.start,
                children: [
                  Text(title, style: const TextStyle(color: Colors.white, fontSize: 16, fontWeight: FontWeight.w600)),
                  const SizedBox(height: 3),
                  Text(subtitle, style: TextStyle(color: Colors.grey.shade500, fontSize: 13)),
                ],
              ),
            ),
            const SizedBox(width: 12),
            trailing,
          ],
        ),
      ),
    );
  }

  Widget _divider() => Divider(height: 1, color: Colors.grey.shade800);

  Widget _sectionTitle(String title) {
    return Text(title, style: TextStyle(color: Colors.grey.shade400, fontSize: 13, fontWeight: FontWeight.w600));
  }

  Widget _modeButton(AnnouncementMode mode, String title, String subtitle, {required bool enabled}) {
    final selected = _mode == mode;
    return Expanded(
      child: Opacity(
        opacity: enabled ? 1 : 0.48,
        child: GestureDetector(
          onTap: enabled ? () => _setMode(mode) : null,
          child: Container(
            padding: const EdgeInsets.all(14),
            decoration: BoxDecoration(
              color: selected ? const Color(0xFF22C55E).withValues(alpha: 0.18) : const Color(0xFF111113),
              borderRadius: BorderRadius.circular(12),
              border: Border.all(color: selected ? const Color(0xFF22C55E) : const Color(0xFF2A2A2E)),
            ),
            child: Column(
              crossAxisAlignment: CrossAxisAlignment.start,
              children: [
                Text(title, style: const TextStyle(color: Colors.white, fontSize: 14, fontWeight: FontWeight.w700)),
                const SizedBox(height: 4),
                Text(subtitle, style: TextStyle(color: Colors.grey.shade400, fontSize: 12)),
              ],
            ),
          ),
        ),
      ),
    );
  }

  Widget _slider({
    required String title,
    required String value,
    required double sliderValue,
    required double min,
    required double max,
    required int divisions,
    required ValueChanged<double> onChanged,
    bool enabled = true,
  }) {
    return Opacity(
      opacity: enabled ? 1 : 0.48,
      child: Padding(
        padding: const EdgeInsets.fromLTRB(16, 14, 16, 10),
        child: Column(
          crossAxisAlignment: CrossAxisAlignment.start,
          children: [
            Row(
              children: [
                Expanded(child: Text(title, style: const TextStyle(color: Colors.white, fontSize: 15))),
                Text(value, style: TextStyle(color: Colors.grey.shade400, fontSize: 13)),
              ],
            ),
            Slider(
              value: sliderValue.clamp(min, max),
              min: min,
              max: max,
              divisions: divisions,
              activeColor: const Color(0xFF22C55E),
              inactiveColor: Colors.grey.shade800,
              onChanged: enabled ? onChanged : null,
            ),
          ],
        ),
      ),
    );
  }

  Widget _primaryButton(String label, VoidCallback onTap, {bool enabled = true}) {
    return GestureDetector(
      onTap: enabled ? onTap : null,
      child: Container(
        width: double.infinity,
        padding: const EdgeInsets.symmetric(vertical: 14),
        decoration: BoxDecoration(
          color: enabled ? const Color(0xFF22C55E) : const Color(0xFF3A3A3D),
          borderRadius: BorderRadius.circular(12),
        ),
        child: Center(
          child: Text(label,
              style: TextStyle(
                  color: enabled ? Colors.white : Colors.grey.shade500, fontSize: 15, fontWeight: FontWeight.w700)),
        ),
      ),
    );
  }

  Widget _secondaryButton(String label, VoidCallback onTap, {bool enabled = true}) {
    return GestureDetector(
      onTap: enabled ? onTap : null,
      child: Container(
        width: double.infinity,
        padding: const EdgeInsets.symmetric(vertical: 14),
        decoration: BoxDecoration(
          color: enabled ? Colors.red.withValues(alpha: 0.14) : const Color(0xFF242428),
          borderRadius: BorderRadius.circular(12),
          border: Border.all(color: enabled ? Colors.redAccent.withValues(alpha: 0.45) : const Color(0xFF333337)),
        ),
        child: Center(
          child: Text(
            label,
            style: TextStyle(
              color: enabled ? Colors.redAccent : Colors.grey.shade600,
              fontSize: 15,
              fontWeight: FontWeight.w700,
            ),
          ),
        ),
      ),
    );
  }

  Future<void> _setMode(AnnouncementMode mode) async {
    setState(() => _mode = mode);
    _prefs.localYoloeAnnouncementMode = mode.preferenceValue;
    await ObjectAnnouncementService.instance.stop();
  }

  Future<void> _setEnabled(bool value) async {
    setState(() => _enabled = value);
    _prefs.localYoloeEnabled = value;
    if (!value) await ObjectAnnouncementService.instance.stop();
  }

  Future<void> _setVoiceEnabled(bool value) async {
    setState(() => _voiceEnabled = value);
    _prefs.localYoloeVoiceEnabled = value;
    if (!value) await ObjectAnnouncementService.instance.stop();
  }

  @override
  Widget build(BuildContext context) {
    final bottomPadding = widget.showBackButton ? 32.0 : 132.0 + MediaQuery.paddingOf(context).bottom;

    return Scaffold(
      backgroundColor: const Color(0xFF0D0D0D),
      appBar: AppBar(
        backgroundColor: const Color(0xFF0D0D0D),
        elevation: 0,
        automaticallyImplyLeading: widget.showBackButton,
        leading: widget.showBackButton
            ? IconButton(
                icon: const FaIcon(FontAwesomeIcons.chevronLeft, size: 18),
                onPressed: () => Navigator.of(context).pop(),
              )
            : null,
        title: Text(
          context.l10n.objectAnnouncementsSettingsTitle,
          style: const TextStyle(fontWeight: FontWeight.w600, fontSize: 18),
        ),
        centerTitle: true,
      ),
      body: ListView(
        padding: EdgeInsets.fromLTRB(20, 8, 20, bottomPadding),
        children: [
          Text(
            context.l10n.objectAnnouncementsSettingsSubtitle,
            style: TextStyle(color: Colors.grey.shade400, fontSize: 14),
          ),
          const SizedBox(height: 16),
          _section(
            children: [
              _row(
                title: context.l10n.objectAnnouncementsMainToggleTitle,
                subtitle: context.l10n.objectAnnouncementsMainToggleSubtitle,
                icon: FontAwesomeIcons.eye,
                trailing: Switch(value: _enabled, onChanged: _setEnabled, activeThumbColor: const Color(0xFF22C55E)),
              ),
            ],
          ),
          const SizedBox(height: 16),
          _sectionTitle(context.l10n.objectAnnouncementsModeSectionTitle),
          const SizedBox(height: 8),
          Row(
            children: [
              _modeButton(
                AnnouncementMode.allObjects,
                context.l10n.objectAnnouncementsAllObjectsModeTitle,
                context.l10n.objectAnnouncementsAllObjectsModeSubtitle,
                enabled: _enabled,
              ),
              const SizedBox(width: 10),
              _modeButton(
                AnnouncementMode.heldObjectsOnly,
                context.l10n.objectAnnouncementsHeldObjectsModeTitle,
                context.l10n.objectAnnouncementsHeldObjectsModeSubtitle,
                enabled: _enabled,
              ),
            ],
          ),
          const SizedBox(height: 16),
          _section(
            children: [
              _row(
                title: context.l10n.objectAnnouncementsVoiceTitle,
                subtitle: _voiceEnabled
                    ? context.l10n.objectAnnouncementsVoiceOnSubtitle
                    : context.l10n.objectAnnouncementsVoiceOffSubtitle,
                icon: FontAwesomeIcons.volumeHigh,
                trailing: Switch(
                  value: _voiceEnabled,
                  onChanged: _enabled ? _setVoiceEnabled : null,
                  activeThumbColor: const Color(0xFF22C55E),
                ),
                enabled: _enabled,
              ),
              _divider(),
              Padding(
                padding: const EdgeInsets.all(16),
                child: Row(
                  children: [
                    Expanded(
                      child: _primaryButton(
                        context.l10n.objectAnnouncementsTestVoiceButton,
                        () => ObjectAnnouncementService.instance
                            .speak(context.l10n.objectAnnouncementsTestVoiceMessage, force: true),
                        enabled: _enabled && _voiceEnabled,
                      ),
                    ),
                    const SizedBox(width: 10),
                    Expanded(
                      child: _secondaryButton(
                        context.l10n.stop,
                        ObjectAnnouncementService.instance.stop,
                        enabled: _enabled,
                      ),
                    ),
                  ],
                ),
              ),
            ],
          ),
          const SizedBox(height: 16),
          Container(
            padding: const EdgeInsets.all(16),
            decoration: BoxDecoration(color: const Color(0xFF122019), borderRadius: BorderRadius.circular(16)),
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
          ),
          const SizedBox(height: 16),
          Theme(
            data: Theme.of(context).copyWith(dividerColor: Colors.transparent),
            child: ExpansionTile(
              tilePadding: const EdgeInsets.symmetric(horizontal: 16),
              childrenPadding: EdgeInsets.zero,
              collapsedBackgroundColor: const Color(0xFF1C1C1E),
              backgroundColor: const Color(0xFF1C1C1E),
              collapsedShape: RoundedRectangleBorder(borderRadius: BorderRadius.circular(16)),
              shape: RoundedRectangleBorder(borderRadius: BorderRadius.circular(16)),
              iconColor: Colors.grey.shade400,
              collapsedIconColor: Colors.grey.shade500,
              title: Text(
                context.l10n.objectAnnouncementsAdvancedTitle,
                style: const TextStyle(color: Colors.white, fontWeight: FontWeight.w600),
              ),
              subtitle: Text(context.l10n.objectAnnouncementsAdvancedSubtitle,
                  style: TextStyle(color: Colors.grey.shade500, fontSize: 12)),
              children: [
                _divider(),
                _row(
                  title: context.l10n.objectAnnouncementsInterruptSpeechTitle,
                  subtitle: context.l10n.objectAnnouncementsInterruptSpeechSubtitle,
                  icon: FontAwesomeIcons.forward,
                  trailing: Switch(
                    value: _interruptSpeech,
                    onChanged: _enabled && _voiceEnabled
                        ? (value) {
                            setState(() => _interruptSpeech = value);
                            _prefs.localYoloeInterruptSpeech = value;
                          }
                        : null,
                    activeThumbColor: const Color(0xFF22C55E),
                  ),
                  enabled: _enabled && _voiceEnabled,
                ),
                _divider(),
                _slider(
                  title: context.l10n.objectAnnouncementsSpeechRateTitle,
                  value: _speechRate.toStringAsFixed(2),
                  sliderValue: _speechRate,
                  min: 0.1,
                  max: 1.0,
                  divisions: 9,
                  onChanged: (value) {
                    setState(() => _speechRate = value);
                    _prefs.localYoloeSpeechRate = value;
                  },
                  enabled: _enabled && _voiceEnabled,
                ),
                _divider(),
                _slider(
                  title: context.l10n.objectAnnouncementsQuietTimeTitle,
                  value: '${_announcementCooldown.toStringAsFixed(0)}s',
                  sliderValue: _announcementCooldown,
                  min: 1,
                  max: 10,
                  divisions: 9,
                  onChanged: (value) {
                    setState(() => _announcementCooldown = value);
                    _prefs.localYoloeMinSecondsBetweenAnnouncements = value;
                  },
                  enabled: _enabled && _voiceEnabled,
                ),
                _divider(),
                Padding(
                  padding: const EdgeInsets.fromLTRB(16, 14, 16, 10),
                  child: DropdownButtonFormField<LocalVisionDetectorImplementation>(
                    initialValue: _detectorImplementation,
                    dropdownColor: const Color(0xFF242428),
                    decoration: InputDecoration(
                      labelText: context.l10n.objectAnnouncementsDetectorTitle,
                      labelStyle: TextStyle(color: Colors.grey.shade400),
                      filled: true,
                      fillColor: const Color(0xFF111113),
                      border: OutlineInputBorder(borderRadius: BorderRadius.circular(12), borderSide: BorderSide.none),
                    ),
                    style: const TextStyle(color: Colors.white),
                    items: LocalVisionDetectorImplementation.values
                        .map(
                          (implementation) => DropdownMenuItem(
                            value: implementation,
                            child: Text(implementation.displayName),
                          ),
                        )
                        .toList(),
                    onChanged: (implementation) {
                      if (implementation == null) return;
                      setState(() => _detectorImplementation = implementation);
                      _prefs.localYoloeDetectorImplementation = implementation.preferenceValue;
                    },
                  ),
                ),
                _divider(),
                _slider(
                  title: context.l10n.objectAnnouncementsMaxObjectsSpokenTitle,
                  value: _maxObjectsPerAnnouncement.toString(),
                  sliderValue: _maxObjectsPerAnnouncement.toDouble(),
                  min: 1,
                  max: 5,
                  divisions: 4,
                  onChanged: (value) {
                    setState(() => _maxObjectsPerAnnouncement = value.round());
                    _prefs.localYoloeMaxObjectsPerAnnouncement = value.round();
                  },
                ),
                _divider(),
                _slider(
                  title: context.l10n.objectAnnouncementsConfidenceThresholdTitle,
                  value: '${(_confidenceThreshold * 100).toStringAsFixed(0)}%',
                  sliderValue: _confidenceThreshold,
                  min: 0.05,
                  max: 0.95,
                  divisions: 18,
                  onChanged: (value) {
                    setState(() => _confidenceThreshold = value);
                    _prefs.localYoloeConfidenceThreshold = value;
                  },
                ),
                _divider(),
                _slider(
                  title: context.l10n.objectAnnouncementsHandMatchThresholdTitle,
                  value: _handIouThreshold.toStringAsFixed(2),
                  sliderValue: _handIouThreshold,
                  min: 0,
                  max: 0.5,
                  divisions: 50,
                  onChanged: (value) {
                    setState(() => _handIouThreshold = value);
                    _prefs.localYoloeHandObjectIouThreshold = value;
                  },
                ),
                _divider(),
                _row(
                  title: context.l10n.objectAnnouncementsAdaptiveThrottlingTitle,
                  subtitle: context.l10n.objectAnnouncementsAdaptiveThrottlingSubtitle,
                  icon: FontAwesomeIcons.gaugeHigh,
                  trailing: Switch(
                    value: _adaptiveThrottlingEnabled,
                    onChanged: (value) {
                      setState(() => _adaptiveThrottlingEnabled = value);
                      _prefs.localYoloeAdaptiveThrottlingEnabled = value;
                    },
                    activeThumbColor: const Color(0xFF22C55E),
                  ),
                ),
              ],
            ),
          ),
        ],
      ),
    );
  }
}
