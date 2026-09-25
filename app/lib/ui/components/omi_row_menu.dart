import 'package:flutter/material.dart';

import 'package:omi/ui/components/omi_icon_button.dart';
import 'package:omi/ui/components/omi_sheet.dart';
import 'package:omi/ui/omi_tokens.dart';

/// One entry of a row's long-press menu.
@immutable
class OmiMenuAction {
  const OmiMenuAction({
    required this.icon,
    required this.label,
    required this.onSelected,
    this.isDestructive = false,
  });

  final IconData icon;

  /// Title Case verb: "Open", "Edit", "Select", "Delete".
  final String label;

  /// Runs after the menu has closed, so it may push a page, open a sheet or show a toast.
  final VoidCallback onSelected;

  /// Red: the entry deletes something.
  final bool isDestructive;
}

/// The long-press menu of a list row (memories, tasks, conversations): one shape everywhere.
///
/// A sheet titled with the row's own text, then one ≥52pt row per action, destructive entries
/// last and red. Order entries Open, then editing actions, then Select (multi-select), then
/// Delete. The chosen action runs after the sheet closes.
///
/// ```dart
/// onLongPress: () => showOmiRowMenu(context, title: memory.content, actions: [
///   OmiMenuAction(icon: Icons.open_in_full, label: l10n.open, onSelected: _open),
///   OmiMenuAction(icon: Icons.delete_outline, label: l10n.delete, onSelected: _delete, isDestructive: true),
/// ]);
/// ```
Future<void> showOmiRowMenu(
  BuildContext context, {
  String? title,
  required List<OmiMenuAction> actions,
}) async {
  OmiHaptics.medium();
  final chosen = await showOmiSheet<OmiMenuAction>(
    context: context,
    title: title,
    padding: const EdgeInsets.only(bottom: OmiSpacing.xs),
    builder: (sheetContext) => Column(
      mainAxisSize: MainAxisSize.min,
      children: [
        for (final action in actions) _OmiMenuRow(action: action, onTap: () => Navigator.of(sheetContext).pop(action)),
      ],
    ),
  );
  chosen?.onSelected();
}

class _OmiMenuRow extends StatelessWidget {
  const _OmiMenuRow({required this.action, required this.onTap});

  final OmiMenuAction action;
  final VoidCallback onTap;

  @override
  Widget build(BuildContext context) {
    final color = action.isDestructive ? OmiColors.danger : OmiColors.textPrimary;
    return Semantics(
      button: true,
      excludeSemantics: true,
      label: action.label,
      onTap: onTap,
      child: InkWell(
        onTap: onTap,
        child: ConstrainedBox(
          constraints: const BoxConstraints(minHeight: kOmiMinTapTarget + 8),
          child: Padding(
            padding: const EdgeInsets.symmetric(horizontal: OmiSpacing.md, vertical: OmiSpacing.xs),
            child: Row(
              children: [
                Icon(action.icon, size: 22, color: color),
                const SizedBox(width: OmiSpacing.md),
                Expanded(child: Text(action.label, style: OmiType.body.copyWith(color: color))),
              ],
            ),
          ),
        ),
      ),
    );
  }
}
