import 'dart:ui' show CheckedState, Tristate;

import 'package:flutter/semantics.dart';
import 'package:flutter_test/flutter_test.dart';

/// Flags the brief asked the dump to record. Others exist; these are the ones
/// that decide whether a node is a control, a heading, or a field.
const List<SemanticsAction> kReportedSemanticsActions = [
  SemanticsAction.tap,
  SemanticsAction.longPress,
  SemanticsAction.increase,
  SemanticsAction.decrease,
  SemanticsAction.scrollLeft,
  SemanticsAction.scrollRight,
  SemanticsAction.scrollUp,
  SemanticsAction.scrollDown,
];

final RegExp _omiGrammarLabel = RegExp(r'^omi(\.[a-z0-9_]+)+$');
final RegExp _bareNumber = RegExp(r'^\d+$');
final RegExp _iconDataDebug = RegExp(r'^IconData\(U\+');

/// One node from [dumpSemanticsTree]. [identifier] is Flutter's machine id
/// ([SemanticsProperties.identifier]) and is never treated as an accessible
/// name — that is the separation B2 must keep.
class SemanticsNodeDump {
  const SemanticsNodeDump({
    required this.id,
    required this.depth,
    required this.label,
    required this.value,
    required this.hint,
    required this.tooltip,
    required this.identifier,
    required this.flags,
    required this.actions,
  });

  final int id;
  final int depth;
  final String label;
  final String value;
  final String hint;
  final String tooltip;
  final String identifier;
  final List<String> flags;
  final List<String> actions;

  bool get isButton => flags.contains('button');
  bool get isHeader => flags.contains('header');
  bool get isTextField => flags.contains('textField');
  bool get isImage => flags.contains('image');
  bool get isLink => flags.contains('link');

  /// A node a screen reader can activate, edit, or scroll.
  bool get isInteractive => isActivateControl || isScrollable;

  /// Activate/edit, not merely a scrollable viewport.
  bool get isActivateControl =>
      isButton ||
      isTextField ||
      isLink ||
      flags.contains('slider') ||
      flags.contains('checked') ||
      flags.contains('toggled') ||
      actions.contains('tap') ||
      actions.contains('longPress') ||
      actions.contains('increase') ||
      actions.contains('decrease');

  bool get isScrollable => actions.any((action) => action.startsWith('scroll'));

  /// Spoken name: label, then value, then hint, then tooltip. Identifier is
  /// excluded on purpose — Flutter does not expose it to users.
  String get accessibleName {
    for (final part in [label, value, hint, tooltip]) {
      if (part.trim().isNotEmpty) return part.trim();
    }
    return '';
  }

  bool get hasAccessibleName => accessibleName.isNotEmpty;

  String? get unhelpfulReason {
    final name = accessibleName;
    if (name.isEmpty) return 'empty';
    if (_omiGrammarLabel.hasMatch(name)) return 'omi-grammar';
    if (_bareNumber.hasMatch(name)) return 'bare-number';
    if (_iconDataDebug.hasMatch(name)) return 'icon-data';
    return null;
  }

  bool get isUnhelpful => unhelpfulReason != null;

  String get line {
    final parts = <String>[
      '${'  ' * depth}#$id',
      if (flags.isNotEmpty) 'flags=${flags.join(',')}',
      if (actions.isNotEmpty) 'actions=${actions.join(',')}',
      if (label.isNotEmpty) 'label=${_quote(label)}',
      if (value.isNotEmpty) 'value=${_quote(value)}',
      if (hint.isNotEmpty) 'hint=${_quote(hint)}',
      if (tooltip.isNotEmpty) 'tooltip=${_quote(tooltip)}',
      if (identifier.isNotEmpty) 'identifier=${_quote(identifier)}',
      if (isInteractive && !hasAccessibleName) 'UNNAMED',
      if (isInteractive && hasAccessibleName && isUnhelpful) 'UNHELPFUL($unhelpfulReason)',
    ];
    return parts.join(' ');
  }

  static String _quote(String value) => '"${value.replaceAll('"', r'\"')}"';
}

class SemanticsTreeDump {
  const SemanticsTreeDump({required this.nodes});

  final List<SemanticsNodeDump> nodes;

  List<SemanticsNodeDump> get interactive => nodes.where((node) => node.isInteractive).toList();

  List<SemanticsNodeDump> get unnamedInteractive =>
      interactive.where((node) => node.isActivateControl && !node.hasAccessibleName).toList();

  List<SemanticsNodeDump> get unnamedScrollables =>
      nodes.where((node) => node.isScrollable && !node.isActivateControl && !node.hasAccessibleName).toList();

  List<SemanticsNodeDump> get unhelpfulInteractive =>
      interactive.where((node) => node.hasAccessibleName && node.isUnhelpful).toList();

  List<SemanticsNodeDump> get headers => nodes.where((node) => node.isHeader).toList();

  List<SemanticsNodeDump> get unnamedImages => nodes.where((node) => node.isImage && !node.hasAccessibleName).toList();

  /// Interactive nodes that share a non-empty accessible name with another
  /// interactive node. Same spoken name on distinct controls.
  Map<String, List<SemanticsNodeDump>> get duplicatedLabels {
    final grouped = <String, List<SemanticsNodeDump>>{};
    for (final node in interactive) {
      final name = node.accessibleName;
      if (name.isEmpty) continue;
      grouped.putIfAbsent(name, () => []).add(node);
    }
    grouped.removeWhere((_, group) => group.length < 2);
    return grouped;
  }

  int get duplicatedLabelControlCount => duplicatedLabels.values.fold<int>(0, (sum, group) => sum + group.length);

  String get treeText => nodes.map((node) => node.line).join('\n');
}

class SurfaceSemanticsReport {
  SurfaceSemanticsReport({
    required this.surface,
    required this.pumpedWidget,
    this.failureReason,
    this.dump,
    this.notes = const [],
  });

  final String surface;
  final String pumpedWidget;
  final String? failureReason;
  final SemanticsTreeDump? dump;
  final List<String> notes;

  bool get pumped => dump != null;

  String get summary {
    if (dump == null) {
      return '$surface: NOT PUMPED ($pumpedWidget) — $failureReason';
    }
    final tree = dump!;
    return [
      '$surface ($pumpedWidget): nodes=${tree.nodes.length} interactive=${tree.interactive.length} '
          'unnamed-controls=${tree.unnamedInteractive.length} '
          'unnamed-scroll=${tree.unnamedScrollables.length} '
          'unhelpful=${tree.unhelpfulInteractive.length} '
          'dup-labels=${tree.duplicatedLabels.length} names / ${tree.duplicatedLabelControlCount} nodes '
          'headers=${tree.headers.length} '
          'unnamed-images=${tree.unnamedImages.length}',
      if (notes.isNotEmpty) '  notes: ${notes.join('; ')}',
    ].join('\n');
  }
}

/// Walk the current semantics tree. Call [WidgetTester.ensureSemantics] first.
SemanticsTreeDump dumpSemanticsTree(WidgetTester tester) {
  final owner = tester.binding.pipelineOwner.semanticsOwner;
  if (owner == null) {
    throw StateError('dumpSemanticsTree requires tester.ensureSemantics()');
  }
  final root = owner.rootSemanticsNode;
  if (root == null) {
    throw StateError('semantics owner has no root node');
  }
  final nodes = <SemanticsNodeDump>[];
  void walk(SemanticsNode node, int depth) {
    nodes.add(_fromData(node.id, depth, node.getSemanticsData()));
    node.visitChildren((child) {
      walk(child, depth + 1);
      return true;
    });
  }

  walk(root, 0);
  return SemanticsTreeDump(nodes: nodes);
}

SemanticsNodeDump _fromData(int id, int depth, SemanticsData data) {
  final flags = data.flagsCollection;
  final flagNames = <String>[
    if (flags.isButton) 'button',
    if (flags.isHeader) 'header',
    if (flags.isTextField) 'textField',
    if (flags.isImage) 'image',
    if (flags.isLink) 'link',
    if (flags.isSlider) 'slider',
    if (flags.isEnabled == Tristate.isTrue) 'enabled',
    if (flags.isEnabled == Tristate.isFalse) 'disabled',
    if (flags.isFocused != Tristate.none) 'focusable',
    if (flags.isFocused == Tristate.isTrue) 'focused',
    if (flags.isSelected == Tristate.isTrue) 'selected',
    if (flags.isChecked != CheckedState.none) 'checked',
    if (flags.isToggled != Tristate.none) 'toggled',
  ];
  final actionNames = [
    for (final action in kReportedSemanticsActions)
      if (data.hasAction(action)) action.name,
  ];
  return SemanticsNodeDump(
    id: id,
    depth: depth,
    label: data.label,
    value: data.value,
    hint: data.hint,
    tooltip: data.tooltip,
    identifier: data.identifier,
    flags: flagNames,
    actions: actionNames,
  );
}
