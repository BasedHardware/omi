import 'package:flutter/material.dart';

import 'package:omi/ui/components/omi_settings.dart';

import 'ios_native_surface.dart';

/// Projects declarative settings rows while retaining their original mutation callbacks.
/// An unrecognised control keeps the entire page in its existing renderer.
List<NativeSection>? nativeSettingsSections(List<Widget> children, {String? Function(Widget)? trailingText}) {
  final groups = <OmiSettingsGroup>[];
  bool collect(List<Widget> widgets) {
    for (final widget in widgets) {
      if (widget is SizedBox) continue;
      if (widget is Column) {
        if (!collect(widget.children)) return false;
      } else if (widget is OmiSettingsGroup) {
        groups.add(widget);
      } else {
        return false;
      }
    }
    return true;
  }

  if (!collect(children)) return null;
  final sections = <NativeSection>[];
  for (final child in groups) {
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
                ? 'button'
                : 'label',
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
        title: child.header ?? '', footer: [child.headerSubtitle, child.footer].whereType<String>().join('\n')));
  }
  return sections;
}
