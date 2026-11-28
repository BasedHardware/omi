import 'package:flutter/material.dart';

import 'package:font_awesome_flutter/font_awesome_flutter.dart';

import 'package:omi/pages/episodes/live_episode_clock.dart';
import 'package:omi/ui/ui.dart';
import 'package:omi/utils/l10n_extensions.dart';

/// The device page's numbers: battery, how much Omi heard today, and audio still on the device —
/// or, while recordings are catching up, how much is still on its way. A dash marks a value
/// that has yet to be confirmed.
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
    this.showUnknownBattery = false,
    this.batteryStuck = false,
  });

  /// Battery percent, or -1 while the reading is unavailable.
  final int batteryLevel;
  final bool showUnknownBattery;

  /// The pendant's near-empty reading looks stuck; the tile suggests a restart.
  final bool batteryStuck;
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
      if (batteryLevel >= 0 || showUnknownBattery)
        _StatTile(
          key: const Key('device_stat_battery'),
          label: l10n.battery,
          value: batteryLevel >= 0 ? '$batteryLevel%' : '—',
          semanticValue: batteryLevel < 0 ? l10n.unknown : null,
          caption: isCharging
              ? l10n.charging
              : batteryStuck
                  ? l10n.batteryRestartToRefresh
                  : null,
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
    // One plain line, battery · on device: no boxes, so the numbers read as text.
    return Wrap(
      spacing: OmiSpacing.xs,
      runSpacing: OmiSpacing.xxs,
      crossAxisAlignment: WrapCrossAlignment.center,
      children: [
        for (var i = 0; i < tiles.length; i++) ...[
          if (i > 0) Text('·', style: OmiType.subhead.copyWith(color: OmiColors.textTertiary)),
          tiles[i],
        ],
      ],
    );
  }

  static int _minutes(int seconds) => seconds < 60 ? seconds : (seconds ~/ 60) * 60;
}

class _StatTile extends StatelessWidget {
  const _StatTile({
    super.key,
    required this.label,
    required this.value,
    this.semanticValue,
    this.caption,
    this.secondCaption,
    this.onTap,
  });

  final String label;
  final String value;
  final String? semanticValue;
  final String? caption;

  /// A second caption after the first, in the same style.
  final String? secondCaption;

  /// A tappable tile ends its caption with a chevron; the whole line is the target.
  final VoidCallback? onTap;

  @override
  Widget build(BuildContext context) {
    final captionStyle = OmiType.subhead.copyWith(color: OmiColors.textSecondary);
    // Wraps rather than overflows when a caption is long or the text size is large.
    final content = Wrap(
      crossAxisAlignment: WrapCrossAlignment.center,
      spacing: OmiSpacing.xxs,
      children: [
        Text(label, style: captionStyle),
        Text(value, style: OmiType.subhead.copyWith(fontWeight: FontWeight.w600)),
        if (caption != null) Text(caption!, style: captionStyle),
        if (secondCaption != null) Text(secondCaption!, style: captionStyle),
        if (onTap != null)
          Icon(
            Icons.chevron_right,
            size: MediaQuery.textScalerOf(context).scale(captionStyle.fontSize!),
            color: OmiColors.textTertiary,
          ),
      ],
    );
    return Semantics(
      label: [label, semanticValue ?? value, if (caption != null) caption!, if (secondCaption != null) secondCaption!]
          .join(', '),
      button: onTap != null,
      excludeSemantics: true,
      onTap: onTap,
      child: onTap == null
          ? content
          : InkWell(
              onTap: onTap,
              child: ConstrainedBox(
                constraints: const BoxConstraints(minWidth: 44, minHeight: 44),
                child: Align(widthFactor: 1, heightFactor: 1, child: content),
              ),
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
