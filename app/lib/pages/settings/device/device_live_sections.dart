import 'dart:async';

import 'package:flutter/material.dart';

import 'package:font_awesome_flutter/font_awesome_flutter.dart';

import 'package:omi/gen/pigeon_communicator.g.dart';
import 'package:omi/pages/episodes/live_episode_clock.dart';
import 'package:omi/ui/ui.dart';
import 'package:omi/utils/l10n_extensions.dart';

/// The device page's numbers: battery, how much Omi heard today, and audio still on the device —
/// or, while recordings are catching up, how much is still on its way. Every value is measured; a
/// stat with nothing to show is left out rather than invented.
class DeviceStatsRow extends StatelessWidget {
  const DeviceStatsRow({
    super.key,
    required this.batteryLevel,
    required this.isCharging,
    required this.heardTodaySeconds,
    required this.onDeviceSeconds,
    this.phoneQueueSeconds = 0,
    this.catchUpSeconds,
    this.catchUpCaption,
    this.onOpenCatchUp,
  });

  /// Battery percent, or <= 0 when the device has not reported one.
  final int batteryLevel;
  final bool isCharging;
  final int heardTodaySeconds;
  final int onDeviceSeconds;

  /// Audio recorded on the phone still waiting for its upload: the On Device
  /// tile names it so hours of phone queue never read as nothing to sync.
  final int phoneQueueSeconds;

  /// Audio still on its way to becoming conversations. While set, the third tile reads
  /// "Catching up" with this duration (a dash when the work has no measured length yet) and
  /// opens On the Way; null when nothing is pending, and the tile is On Device again.
  final int? catchUpSeconds;

  /// What the catch-up is waiting on ("when online"); the tile adds the chevron.
  final String? catchUpCaption;
  final VoidCallback? onOpenCatchUp;

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
      if (catchUpSeconds case final seconds?)
        _StatTile(
          key: const Key('device_stat_catching_up'),
          label: l10n.deviceCatchingUp,
          value: seconds > 0 ? OmiDuration.compact(_minutes(seconds), l10n) : '—',
          caption: catchUpCaption,
          onTap: onOpenCatchUp,
        )
      else
        _StatTile(
          key: const Key('device_stat_on_device'),
          label: l10n.onDevice,
          value: OmiDuration.compact(_minutes(onDeviceSeconds), l10n),
          caption: onDeviceSeconds > 0 ? l10n.deviceToSync : null,
          secondCaption:
              phoneQueueSeconds > 0 ? l10n.deviceOnPhoneQueue(OmiDuration.compact(phoneQueueSeconds, l10n)) : null,
        ),
    ];
    // One row height for every tile: the tallest tile's captions (usually On
    // Device's phone-queue line) raise the whole row, so a captioned tile never
    // towers over its neighbours. IntrinsicHeight + stretch sizes the row to
    // its own content only — never to whatever height the viewport has left.
    return IntrinsicHeight(
      child: Row(
        crossAxisAlignment: CrossAxisAlignment.stretch,
        children: [
          for (var i = 0; i < tiles.length; i++) ...[
            if (i > 0) const SizedBox(width: OmiSpacing.xs),
            Expanded(child: tiles[i]),
          ],
        ],
      ),
    );
  }

  static int _minutes(int seconds) => seconds < 60 ? seconds : (seconds ~/ 60) * 60;
}

class _StatTile extends StatelessWidget {
  const _StatTile({super.key, required this.label, required this.value, this.caption, this.secondCaption, this.onTap});

  final String label;
  final String value;
  final String? caption;

  /// A second line under the caption, in the same style.
  final String? secondCaption;

  /// A tappable tile ends its caption with a chevron; the whole tile is the target.
  final VoidCallback? onTap;

  @override
  Widget build(BuildContext context) {
    final captionStyle = OmiType.footnote.copyWith(color: OmiColors.textSecondary);
    final content = Container(
      constraints: const BoxConstraints(minHeight: 84),
      padding: const EdgeInsets.all(OmiSpacing.sm),
      // Min, not max: the tile floors at 84 and otherwise sizes to its own
      // lines — the row's IntrinsicHeight shares the tallest tile's height,
      // never whatever height the viewport has left over.
      child: Column(
        mainAxisSize: MainAxisSize.min,
        mainAxisAlignment: MainAxisAlignment.start,
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          Text(label, style: OmiType.footnote.copyWith(color: OmiColors.textTertiary)),
          const SizedBox(height: OmiSpacing.xxs),
          Text(value, style: OmiType.title3, maxLines: 1, overflow: TextOverflow.ellipsis),
          if (caption != null || onTap != null) ...[
            const SizedBox(height: 2),
            Text.rich(
              TextSpan(children: [
                if (caption != null) TextSpan(text: caption),
                if (onTap != null)
                  WidgetSpan(
                    alignment: PlaceholderAlignment.middle,
                    // Mirrors itself in right-to-left locales; scales with the caption.
                    child: Icon(
                      Icons.chevron_right,
                      size: MediaQuery.textScalerOf(context).scale(captionStyle.fontSize!),
                      color: OmiColors.textTertiary,
                    ),
                  ),
              ]),
              style: captionStyle,
            ),
          ],
          if (secondCaption != null) ...[
            const SizedBox(height: 2),
            Text(secondCaption!, style: captionStyle),
          ],
        ],
      ),
    );
    return Semantics(
      label: [label, value, if (caption != null) caption!, if (secondCaption != null) secondCaption!].join(', '),
      button: onTap != null,
      excludeSemantics: true,
      child: Material(
        color: OmiColors.surface1,
        borderRadius: OmiRadius.lgAll,
        clipBehavior: Clip.antiAlias,
        child: onTap == null ? content : InkWell(onTap: onTap, child: content),
      ),
    );
  }
}

/// Right now: the live episode this device is feeding. Offline audio catching up is the stat
/// row's Catching up tile, not a row here.
class DeviceRightNowGroup extends StatelessWidget {
  const DeviceRightNowGroup({
    super.key,
    this.liveTitle,
    this.liveLength,
    this.liveLengthNow,
    this.liveSubtitle,
    this.liveProblem = false,
    this.onFixProblem,
    this.onOpenLive,
  });

  final String? liveTitle;
  final String? liveLength;

  /// The running length read fresh each second; only the live row re-renders, not the page.
  final String Function(DateTime now)? liveLengthNow;

  /// A fixed subtitle instead of a running length: "Connecting…" while the pendant's
  /// audio is still being verified, or the failure sentence when [liveProblem] is set.
  final String? liveSubtitle;

  /// The live row is a failure the reader can act on ([onFixProblem]); no length, no clock.
  final bool liveProblem;
  final VoidCallback? onFixProblem;

  final VoidCallback? onOpenLive;

  bool get hasContent => liveTitle != null;

  Widget _liveRow(String subtitle) => OmiSettingsRow(
        key: const Key('device_right_now_live'),
        leading: const OmiLiveDot(size: 8),
        title: liveTitle!,
        subtitle: subtitle,
        onTap: onOpenLive,
      );

  /// The pendant owes audio: the row names the failure and its tap is the fix.
  Widget _problemRow() => OmiSettingsRow(
        key: const Key('device_right_now_no_audio'),
        leading: Icon(Icons.warning_amber_rounded, color: OmiColors.warning),
        title: liveTitle!,
        subtitle: liveSubtitle,
        onTap: onFixProblem,
      );

  @override
  Widget build(BuildContext context) {
    final l10n = context.l10n;
    return OmiSettingsGroup(
      header: l10n.deviceRightNow,
      children: [
        if (liveTitle != null)
          liveProblem
              ? _problemRow()
              : liveSubtitle != null
                  ? _liveRow(liveSubtitle!)
                  : liveLengthNow == null
                      ? _liveRow(l10n.deviceLiveEpisode(liveLength ?? ''))
                      : LiveEpisodeClock(
                          clock: DateTime.now,
                          builder: (context, now) => _liveRow(l10n.deviceLiveEpisode(liveLengthNow!(now))),
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
