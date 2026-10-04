import 'package:flutter/material.dart';
import 'package:font_awesome_flutter/font_awesome_flutter.dart';

import 'package:omi/ui/components/omi_settings.dart';

import 'ios_native_surface.dart';

/// Projects declarative settings rows while retaining their original mutation callbacks.
/// An unrecognised control keeps the entire page in its existing renderer.
List<NativeSection>? nativeSettingsSections(List<Widget> children, {String? Function(Widget)? trailingText}) {
  final groups = <({OmiSettingsGroup group, OmiSectionHeader? header})>[];
  OmiSectionHeader? pendingHeader;
  bool collect(List<Widget> widgets) {
    for (final widget in widgets) {
      if (widget is SizedBox) continue;
      if (widget is Column) {
        if (!collect(widget.children)) return false;
      } else if (widget is OmiSectionHeader) {
        if (pendingHeader != null || (widget.trailing != null && trailingText?.call(widget.trailing!) == null)) {
          return false;
        }
        pendingHeader = widget;
      } else if (widget is OmiSettingsGroup) {
        groups.add((group: widget, header: pendingHeader));
        pendingHeader = null;
      } else {
        return false;
      }
    }
    return true;
  }

  if (!collect(children) || pendingHeader != null) return null;
  final sections = <NativeSection>[];
  for (final entry in groups) {
    final child = entry.group;
    final rows = <NativeRow>[];
    for (final control in child.children) {
      if (control is! OmiSettingsRow) return null;
      final trailing = control.trailing == null ? null : trailingText?.call(control.trailing!);
      if (control.trailing != null && trailing == null) return null;
      final id = control.key is ValueKey<String>
          ? (control.key! as ValueKey<String>).value
          : 'setting_${sections.length}_${rows.length}';
      rows.add(NativeRow(
        id,
        control.title,
        subtitle:
            [control.subtitle, control.value, trailing].whereType<String>().where((text) => text.isNotEmpty).join('\n'),
        kind: control.toggleValue != null
            ? 'toggle'
            : control.onTap != null
                ? (control.showChevron ?? control.trailing == null)
                    ? 'navigation'
                    : 'button'
                : 'label',
        symbol: _settingsSymbol(control.leading),
        value: control.toggleValue,
        destructive: control.isDestructive,
        action: control.toggleValue != null
            ? control.onToggle == null
                ? null
                : (value) {
                    control.onToggle!(value as bool);
                  }
            : control.onTap == null
                ? null
                : (_) {
                    control.onTap!();
                  },
      ));
    }
    sections.add(NativeSection('settings_group_${sections.length}', rows,
        title: child.header ?? entry.header?.title ?? '',
        footer: [
          entry.header?.subtitle,
          if (entry.header?.trailing != null) trailingText?.call(entry.header!.trailing!),
          child.headerSubtitle,
          child.footer,
        ].whereType<String>().join('\n')));
  }
  return sections;
}

String? _settingsSymbol(Widget? leading) {
  if (leading is! FaIcon) return null;
  return _settingsSymbols[leading.icon];
}

final _settingsSymbols = <IconData, String>{
  FontAwesomeIcons.solidUser.data: 'person.crop.circle',
  FontAwesomeIcons.chartLine.data: 'chart.xyaxis.line',
  FontAwesomeIcons.gift.data: 'gift',
  FontAwesomeIcons.bluetooth.data: 'antenna.radiowaves.left.and.right',
  FontAwesomeIcons.microphone.data: 'mic',
  FontAwesomeIcons.volumeHigh.data: 'speaker.wave.2',
  FontAwesomeIcons.solidBell.data: 'bell',
  FontAwesomeIcons.networkWired.data: 'point.3.connected.trianglepath.dotted',
  FontAwesomeIcons.shield.data: 'shield',
  FontAwesomeIcons.shieldHalved.data: 'checkmark.shield',
  FontAwesomeIcons.brain.data: 'brain',
  FontAwesomeIcons.bullseye.data: 'target',
  FontAwesomeIcons.circleQuestion.data: 'questionmark.circle',
  FontAwesomeIcons.solidEnvelope.data: 'envelope',
  FontAwesomeIcons.code.data: 'chevron.left.forwardslash.chevron.right',
  FontAwesomeIcons.solidCloud.data: 'icloud',
  FontAwesomeIcons.phone.data: 'phone',
  FontAwesomeIcons.globe.data: 'globe',
  FontAwesomeIcons.book.data: 'book',
  FontAwesomeIcons.waveSquare.data: 'waveform',
  FontAwesomeIcons.users.data: 'person.2',
  FontAwesomeIcons.clock.data: 'clock',
  FontAwesomeIcons.floppyDisk.data: 'internaldrive',
  FontAwesomeIcons.towerBroadcast.data: 'antenna.radiowaves.left.and.right',
};
