import 'dart:async';

import 'package:flutter/material.dart';

import 'package:font_awesome_flutter/font_awesome_flutter.dart';

import 'package:omi/gen/pigeon_communicator.g.dart';
import 'package:omi/pages/episodes/live_episode_clock.dart';
import 'package:omi/pages/settings/device/device_catching_up_card.dart';
import 'package:omi/ui/ui.dart';
import 'package:omi/utils/l10n_extensions.dart';

/// The device page's numbers: battery, how much Omi heard today, and audio still on the device.
/// Every value is measured; a stat with nothing to show is left out rather than invented.
class DeviceStatsRow extends StatelessWidget {
  const DeviceStatsRow({
    super.key,
    required this.batteryLevel,
    required this.isCharging,
    required this.heardTodaySeconds,
    required this.onDeviceSeconds,
  });

  /// Battery percent, or <= 0 when the device has not reported one.
  final int batteryLevel;
  final bool isCharging;
  final int heardTodaySeconds;
  final int onDeviceSeconds;

  @override
  Widget build(BuildContext context) {
    final l10n = context.l10n;
    final tiles = <Widget>[
      if (batteryLevel > 0)
        _StatTile(
          key: const Key('device_stat_battery'),
          label: l10n.battery,
          value: '$batteryLevel%',
          caption: isCharging ? l10n.charging : null,
        ),
      _StatTile(
        key: const Key('device_stat_heard_today'),
        label: l10n.deviceHeardToday,
        value: OmiDuration.compact(_minutes(heardTodaySeconds), l10n),
      ),
      _StatTile(
        key: const Key('device_stat_on_device'),
        label: l10n.onDevice,
        value: OmiDuration.compact(_minutes(onDeviceSeconds), l10n),
        caption: onDeviceSeconds > 0 ? l10n.deviceToSync : null,
      ),
    ];
    return Row(
      crossAxisAlignment: CrossAxisAlignment.start,
      children: [
        for (var i = 0; i < tiles.length; i++) ...[
          if (i > 0) const SizedBox(width: OmiSpacing.xs),
          Expanded(child: tiles[i]),
        ],
      ],
    );
  }

  static int _minutes(int seconds) => seconds < 60 ? seconds : (seconds ~/ 60) * 60;
}

class _StatTile extends StatelessWidget {
  const _StatTile({super.key, required this.label, required this.value, this.caption});

  final String label;
  final String value;
  final String? caption;

  @override
  Widget build(BuildContext context) {
    return Semantics(
      label: [label, value, if (caption != null) caption!].join(', '),
      excludeSemantics: true,
      child: Container(
        constraints: const BoxConstraints(minHeight: 84),
        padding: const EdgeInsets.all(OmiSpacing.sm),
        decoration: BoxDecoration(color: OmiColors.surface1, borderRadius: OmiRadius.lgAll),
        child: Column(
          crossAxisAlignment: CrossAxisAlignment.start,
          children: [
            Text(label, style: OmiType.footnote.copyWith(color: OmiColors.textTertiary)),
            const SizedBox(height: OmiSpacing.xxs),
            Text(value, style: OmiType.title3, maxLines: 1, overflow: TextOverflow.ellipsis),
            if (caption != null) ...[
              const SizedBox(height: 2),
              Text(caption!, style: OmiType.footnote.copyWith(color: OmiColors.textSecondary)),
            ],
          ],
        ),
      ),
    );
  }
}

/// Right now: the live episode this device is feeding, and offline audio catching up.
class DeviceRightNowGroup extends StatelessWidget {
  const DeviceRightNowGroup({
    super.key,
    this.liveTitle,
    this.liveLength,
    this.liveLengthNow,
    this.onOpenLive,
    this.catchingUp,
    this.onOpenCatchingUp,
  });

  final String? liveTitle;
  final String? liveLength;

  /// The running length read fresh each second; only the live row re-renders, not the page.
  final String Function(DateTime now)? liveLengthNow;
  final VoidCallback? onOpenLive;

  final DeviceCatchUpSummary? catchingUp;
  final VoidCallback? onOpenCatchingUp;

  bool get hasContent => liveTitle != null || catchingUp != null;

  Widget _liveRow(String subtitle) => OmiSettingsRow(
        key: const Key('device_right_now_live'),
        leading: const OmiLiveDot(size: 8),
        title: liveTitle!,
        subtitle: subtitle,
        onTap: onOpenLive,
      );

  @override
  Widget build(BuildContext context) {
    final l10n = context.l10n;
    final catchingUp = this.catchingUp;
    return OmiSettingsGroup(
      header: l10n.deviceRightNow,
      children: [
        if (liveTitle != null)
          liveLengthNow == null
              ? _liveRow(l10n.deviceLiveEpisode(liveLength ?? ''))
              : LiveEpisodeClock(
                  clock: DateTime.now,
                  builder: (context, now) => _liveRow(l10n.deviceLiveEpisode(liveLengthNow!(now))),
                ),
        if (catchingUp != null)
          DeviceCatchingUpCard(
            key: const Key('device_right_now_catching_up'),
            summary: catchingUp,
            onOpen: onOpenCatchingUp,
          ),
      ],
    );
  }
}

/// Recently: when this device dropped and for how long, from the phone's own connection history.
class DeviceRecentlyGroup extends StatefulWidget {
  const DeviceRecentlyGroup({super.key, required this.load, this.now});

  /// The device's native disconnect history (newest last).
  final Future<List<BleDisconnectEvent>> Function() load;
  final DateTime Function()? now;

  @override
  State<DeviceRecentlyGroup> createState() => _DeviceRecentlyGroupState();
}

class _DeviceRecentlyGroupState extends State<DeviceRecentlyGroup> {
  List<BleDisconnectEvent> _events = const [];

  static const _window = Duration(hours: 24);
  static const _limit = 4;

  @override
  void initState() {
    super.initState();
    unawaited(_load());
  }

  Future<void> _load() async {
    try {
      final history = await widget.load();
      final now = (widget.now ?? DateTime.now)();
      final recent = [
        for (final event in history.reversed)
          if (event.eventType != 'fail_to_connect' &&
              !event.isManual &&
              event.timeToReconnectMs > 0 &&
              now.difference(DateTime.fromMillisecondsSinceEpoch(event.timestamp)) <= _window)
            event
      ].take(_limit).toList();
      if (mounted) setState(() => _events = recent);
    } catch (_) {
      // Diagnostics are best-effort: no history, no section.
    }
  }

  @override
  Widget build(BuildContext context) {
    if (_events.isEmpty) return const SizedBox.shrink();
    final l10n = context.l10n;
    final dates = OmiDateFormat.of(context);
    return Padding(
      padding: const EdgeInsets.only(bottom: OmiSpacing.xxl),
      child: OmiSettingsGroup(
        key: const Key('device_recently'),
        header: l10n.deviceRecently,
        children: [
          for (final event in _events)
            OmiSettingsRow(
              leading: Icon(Icons.bluetooth_disabled_rounded, color: OmiColors.warning),
              title: l10n.deviceDisconnectedFor(OmiDuration.compact((event.timeToReconnectMs / 1000).round(), l10n)),
              value: dates.time(DateTime.fromMillisecondsSinceEpoch(event.timestamp)),
              showChevron: false,
            ),
        ],
      ),
    );
  }
}

/// Controls: pause and resume recording on this device.
class DeviceControlsGroup extends StatelessWidget {
  const DeviceControlsGroup({super.key, required this.paused, required this.onToggle});

  final bool paused;
  final VoidCallback? onToggle;

  @override
  Widget build(BuildContext context) {
    final l10n = context.l10n;
    return OmiSettingsGroup(
      header: l10n.deviceControls,
      children: [
        OmiSettingsRow(
          key: const Key('device_pause_recording'),
          leading: FaIcon(paused ? FontAwesomeIcons.play : FontAwesomeIcons.pause),
          title: paused ? l10n.resumeRecording : l10n.pauseRecording,
          showChevron: false,
          onTap: onToggle,
        ),
      ],
    );
  }
}
