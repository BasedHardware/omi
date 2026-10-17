import 'package:flutter/material.dart';

import 'package:omi/ui/components/omi_button.dart';

import 'ios_native_surface.dart';

/// Projects an existing, declared action group without reproducing its state decisions.
/// Unknown controls retain the entire original surface instead of dropping an action.
List<NativeRow>? nativeButtonRows(Iterable<Widget> widgets, {required String prefix}) {
  final rows = <NativeRow>[];
  bool visit(Widget widget) {
    final key = widget.key;
    final id = '${prefix}_${key is ValueKey<String> ? key.value : rows.length}';
    if (widget is OmiButton) {
      rows.add(NativeRow(id, widget.label,
          enabled: widget.onPressed != null && !widget.isLoading,
          destructive: widget.variant == OmiButtonVariant.destructive,
          action: widget.onPressed == null ? null : (_) async => await widget.onPressed!()));
      return true;
    }
    if (widget is TextButton && widget.child is Text) {
      final label = (widget.child as Text).data;
      if (label == null) return false;
      rows.add(NativeRow(id, label,
          enabled: widget.onPressed != null, action: widget.onPressed == null ? null : (_) => widget.onPressed!()));
      return true;
    }
    if (widget is Wrap) return widget.children.every(visit);
    if (widget is Flex) return widget.children.every(visit);
    if (widget is Align) return widget.child == null || visit(widget.child!);
    if (widget is Padding) return widget.child == null || visit(widget.child!);
    if (widget is SizedBox) return widget.child == null || visit(widget.child!);
    return false;
  }

  if (!widgets.every(visit) || rows.map((row) => row.id).toSet().length != rows.length) return null;
  return rows;
}
