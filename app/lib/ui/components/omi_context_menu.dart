import 'dart:ui' as ui;

import 'package:flutter/material.dart';

import 'package:omi/ui/components/omi_row_menu.dart';
import 'package:omi/ui/omi_tokens.dart';

/// A row's long-press context menu (v2 `ContextMenu`): the pressed row stays sharp where it is
/// while everything else frosts and dims, and a compact menu opens under it (above it when the row
/// sits near the bottom). Each entry is its label then its glyph; destructive entries come last,
/// after a gap, in red. The chosen action runs after the menu closes. Tapping outside closes it.
///
/// [anchor] is the row's rect in global coordinates.
Future<void> showOmiContextMenu(
  BuildContext context, {
  required Rect anchor,
  required List<OmiMenuAction> actions,
}) async {
  OmiHaptics.medium();
  final chosen = await Navigator.of(context, rootNavigator: true).push<OmiMenuAction>(
    PageRouteBuilder<OmiMenuAction>(
      opaque: false,
      barrierDismissible: true,
      barrierColor: Colors.transparent,
      transitionDuration: OmiMotion.of(context).quick,
      reverseTransitionDuration: OmiMotion.of(context).quick,
      pageBuilder: (routeContext, animation, _) =>
          _OmiContextMenuOverlay(anchor: anchor, actions: actions, animation: animation),
    ),
  );
  chosen?.onSelected();
}

class _OmiContextMenuOverlay extends StatelessWidget {
  const _OmiContextMenuOverlay({required this.anchor, required this.actions, required this.animation});

  final Rect anchor;
  final List<OmiMenuAction> actions;
  final Animation<double> animation;

  static const double _menuWidth = 250;
  static const double _rowHeight = 46;
  static const double _groupGap = 8;

  @override
  Widget build(BuildContext context) {
    final size = MediaQuery.sizeOf(context);
    final insets = MediaQuery.paddingOf(context);
    final regular = actions.where((a) => !a.isDestructive).toList();
    final destructive = actions.where((a) => a.isDestructive).toList();
    final menuHeight = _rowHeight * actions.length + (regular.isNotEmpty && destructive.isNotEmpty ? _groupGap : 0);
    final below = anchor.bottom + OmiSpacing.xs + menuHeight <= size.height - insets.bottom - OmiSpacing.md;
    final top = below
        ? anchor.bottom + OmiSpacing.xs
        : (anchor.top - OmiSpacing.xs - menuHeight).clamp(insets.top + OmiSpacing.xs, size.height);
    final left = anchor.left.clamp(OmiSpacing.md, size.width - _menuWidth - OmiSpacing.md).toDouble();
    final curved = CurvedAnimation(parent: animation, curve: Curves.easeOutCubic);

    // Frost everything but the row: four panes around it, so the row keeps its own pixels.
    final panes = [
      Rect.fromLTRB(0, 0, size.width, anchor.top),
      Rect.fromLTRB(0, anchor.bottom, size.width, size.height),
      Rect.fromLTRB(0, anchor.top, anchor.left, anchor.bottom),
      Rect.fromLTRB(anchor.right, anchor.top, size.width, anchor.bottom),
    ].where((r) => r.width > 0 && r.height > 0);

    return FadeTransition(
      opacity: curved,
      child: Stack(
        children: [
          for (final pane in panes)
            Positioned.fromRect(
              rect: pane,
              child: ClipRect(
                child: BackdropFilter(
                  filter: ui.ImageFilter.blur(sigmaX: 14, sigmaY: 14),
                  child: ColoredBox(color: OmiColors.scrim),
                ),
              ),
            ),
          Positioned.fill(
            child: GestureDetector(
              key: const ValueKey('omi_context_menu_dismiss'),
              behavior: HitTestBehavior.opaque,
              onTap: () => Navigator.of(context).pop(),
            ),
          ),
          Positioned(
            left: left,
            top: top,
            width: _menuWidth,
            child: ScaleTransition(
              scale: Tween<double>(begin: 0.92, end: 1).animate(curved),
              alignment: below ? Alignment.topLeft : Alignment.bottomLeft,
              child: _MenuCard(regular: regular, destructive: destructive),
            ),
          ),
        ],
      ),
    );
  }
}

class _MenuCard extends StatelessWidget {
  const _MenuCard({required this.regular, required this.destructive});

  final List<OmiMenuAction> regular;
  final List<OmiMenuAction> destructive;

  @override
  Widget build(BuildContext context) {
    Widget rows(List<OmiMenuAction> group) => Column(
          mainAxisSize: MainAxisSize.min,
          children: [
            for (final (i, action) in group.indexed) ...[
              if (i > 0) Divider(height: 0.5, thickness: 0.5, color: OmiColors.border),
              _MenuRow(action: action),
            ],
          ],
        );
    return Material(
      key: const ValueKey('omi_context_menu'),
      color: OmiColors.surface2,
      elevation: 0,
      shadowColor: Colors.transparent,
      shape: const RoundedRectangleBorder(borderRadius: OmiRadius.xlAll),
      clipBehavior: Clip.antiAlias,
      child: Column(
        mainAxisSize: MainAxisSize.min,
        children: [
          if (regular.isNotEmpty) rows(regular),
          if (regular.isNotEmpty && destructive.isNotEmpty)
            Container(height: _OmiContextMenuOverlay._groupGap, color: OmiColors.surface1),
          if (destructive.isNotEmpty) rows(destructive),
        ],
      ),
    );
  }
}

class _MenuRow extends StatelessWidget {
  const _MenuRow({required this.action});

  final OmiMenuAction action;

  @override
  Widget build(BuildContext context) {
    final color = action.isDestructive ? OmiColors.danger : OmiColors.textPrimary;
    void choose() => Navigator.of(context).pop(action);
    return Semantics(
      button: true,
      label: action.label,
      excludeSemantics: true,
      onTap: choose,
      child: InkWell(
        key: action.key,
        onTap: choose,
        splashFactory: NoSplash.splashFactory,
        highlightColor: OmiColors.cellPressed,
        child: SizedBox(
          height: _OmiContextMenuOverlay._rowHeight,
          child: Padding(
            padding: const EdgeInsets.symmetric(horizontal: OmiSpacing.md),
            child: Row(
              children: [
                Expanded(
                  child: Text(
                    action.label,
                    maxLines: 1,
                    overflow: TextOverflow.ellipsis,
                    style: OmiType.body.copyWith(color: color),
                  ),
                ),
                const SizedBox(width: OmiSpacing.sm),
                Icon(action.icon, size: 18, color: color),
              ],
            ),
          ),
        ),
      ),
    );
  }
}
