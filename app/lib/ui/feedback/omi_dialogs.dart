import 'dart:math' as math;
import 'dart:ui' show ImageFilter;

import 'package:flutter/cupertino.dart';
import 'package:flutter/material.dart';

import 'package:omi/ui/omi_tokens.dart';

import 'package:omi/utils/l10n_extensions.dart';

/// The app's single confirmation / alert system (docs/ux-contract.md §5).
///
/// * [showOmiConfirm] — a question with two answers: Cancel and a verb that names the action
///   ("Delete", "Sign Out", "Clear Chat"). Cancel is always shown.
/// * [showOmiConfirmWithOptOut] — the same, plus a "Don't ask again" row. Only for actions an Undo
///   backs; an action that cannot be undone is confirmed every time.
/// * [showOmiAlert] — information with one button.
/// * [OmiAlertDialog] — the widget behind all three, for code that has to hand `showDialog` a
///   widget (the legacy `getDialog` / `ConfirmationDialog` adapters).
/// * [OmiDialogCard] — a dialog that holds a control, such as the "Don't ask again" row.
/// * [showOmiConfirmMenu] — a destructive confirm that pops from the button that asked for it.
///
/// On iOS [OmiAlertDialog] is a `CupertinoAlertDialog` with real `CupertinoDialogAction`s
/// (destructive actions red, the safe choice bold); elsewhere a Material `AlertDialog` with text
/// buttons, the destructive one in [omiDialogDangerColor]. [OmiDialogCard] is Omi's own card on
/// every platform: the system alert is a fixed 270pt and has no room for a control.

/// Destructive action colour on Material dialogs (iOS dark-mode systemRed; legible on every dark surface).
Color get omiDialogDangerColor => OmiColors.danger;

/// One button in an [OmiAlertDialog].
class OmiDialogAction {
  const OmiDialogAction({
    this.key,
    required this.label,
    required this.onPressed,
    this.isDestructive = false,
    this.isDefault = false,
  });

  /// Identifies the rendered action button in tests.
  final Key? key;

  /// A verb naming what the button does ("Delete", "Sign Out"), or Cancel / OK.
  final String label;
  final VoidCallback? onPressed;

  /// Red: the action destroys something.
  final bool isDestructive;

  /// Bold on iOS: the action a reader is expected to take (Cancel, when the other choice is destructive).
  final bool isDefault;
}

/// Whether dialogs on this [context] use the Cupertino look.
///
/// Reads the theme's platform (not `dart:io`) so tests can pin it with `debugDefaultTargetPlatformOverride`.
bool omiUsesCupertinoDialogs(BuildContext context) {
  final platform = Theme.of(context).platform;
  return platform == TargetPlatform.iOS || platform == TargetPlatform.macOS;
}

/// The adaptive alert dialog every Omi confirmation and alert is drawn with.
class OmiAlertDialog extends StatelessWidget {
  const OmiAlertDialog({super.key, this.title, this.message, this.content, required this.actions});

  final String? title;
  final String? message;

  /// Extra content below [message] (e.g. a "Don't ask again" row).
  final Widget? content;
  final List<OmiDialogAction> actions;

  @override
  Widget build(BuildContext context) {
    final body = _body(context);
    if (omiUsesCupertinoDialogs(context)) {
      return CupertinoAlertDialog(
        title: title == null ? null : Text(title!),
        content: body,
        actions: [
          for (final action in actions)
            CupertinoDialogAction(
              key: action.key,
              onPressed: action.onPressed,
              isDestructiveAction: action.isDestructive,
              isDefaultAction: action.isDefault,
              child: Text(action.label),
            ),
        ],
      );
    }
    return AlertDialog(
      scrollable: true,
      title: title == null ? null : Text(title!),
      content: body,
      actions: [
        for (final action in actions)
          TextButton(
            key: action.key,
            onPressed: action.onPressed,
            style: TextButton.styleFrom(
              foregroundColor: action.isDestructive
                  ? omiDialogDangerColor
                  : (OmiColors.active == OmiPalette.light
                      ? OmiColors.textPrimary
                      : (action.isDefault ? Colors.white : Colors.white.withValues(alpha: 0.78))),
              minimumSize: const Size(64, 44),
            ),
            child: Text(
              action.label,
              style: TextStyle(fontWeight: action.isDefault || action.isDestructive ? FontWeight.w600 : null),
            ),
          ),
      ],
    );
  }

  Widget? _body(BuildContext context) {
    if (message == null && content == null) return null;
    if (content == null) return Text(message!);
    return Column(
      mainAxisSize: MainAxisSize.min,
      crossAxisAlignment: omiUsesCupertinoDialogs(context) ? CrossAxisAlignment.center : CrossAxisAlignment.start,
      children: [
        if (message != null) Text(message!),
        if (message != null) const SizedBox(height: 12),
        content!,
      ],
    );
  }
}

/// Result of [showOmiConfirmWithOptOut].
class OmiConfirmResult {
  const OmiConfirmResult({required this.confirmed, required this.dontAskAgain});

  final bool confirmed;

  /// The reader ticked "Don't ask again". Only meaningful when [confirmed]; callers persist it then.
  final bool dontAskAgain;
}

/// Asks [title] with Cancel and [confirmLabel]. Resolves `true` only when the reader chose
/// [confirmLabel]; Cancel, the barrier and system back all resolve `false`.
///
/// [confirmLabel] is a verb naming the action ("Delete", "Sign Out", "Clear Chat"), never "OK" or
/// "Confirm". Set [destructive] when the action destroys something: the button turns red and
/// Cancel becomes the default (bold) choice.
Future<bool> showOmiConfirm(
  BuildContext context, {
  required String title,
  String? message,
  required String confirmLabel,
  bool destructive = false,
  String? cancelLabel,
  bool barrierDismissible = true,
}) async {
  final confirmed = await showDialog<bool>(
    context: context,
    barrierDismissible: barrierDismissible,
    builder: (dialogContext) => OmiAlertDialog(
      title: title,
      message: message,
      actions: _confirmActions(
        dialogContext,
        confirmLabel: confirmLabel,
        cancelLabel: cancelLabel,
        destructive: destructive,
        onCancel: () => Navigator.of(dialogContext).pop(false),
        onConfirm: () => Navigator.of(dialogContext).pop(true),
      ),
    ),
  );
  return confirmed ?? false;
}

/// [showOmiConfirm] with a "Don't ask again" row under the message.
///
/// Contract: offer this only when an Undo backs the action (docs/ux-contract.md §4). The row is a
/// single ≥44pt target — tapping the label toggles it too.
Future<OmiConfirmResult> showOmiConfirmWithOptOut(
  BuildContext context, {
  required String title,
  String? message,
  required String confirmLabel,
  bool destructive = false,
  String? cancelLabel,
  String? optOutLabel,
  bool initialOptOut = false,
  bool barrierDismissible = true,
}) async {
  var dontAskAgain = initialOptOut;
  final confirmed = await showDialog<bool>(
    context: context,
    barrierDismissible: barrierDismissible,
    builder: (dialogContext) => StatefulBuilder(
      builder: (dialogContext, setState) => OmiDialogCard(
        title: title,
        message: message,
        content: OmiCheckboxRow(
          label: optOutLabel ?? dialogContext.l10n.dontAskAgain,
          value: dontAskAgain,
          onChanged: (value) => setState(() => dontAskAgain = value),
        ),
        actions: _confirmActions(
          dialogContext,
          confirmLabel: confirmLabel,
          cancelLabel: cancelLabel,
          destructive: destructive,
          onCancel: () => Navigator.of(dialogContext).pop(false),
          onConfirm: () => Navigator.of(dialogContext).pop(true),
        ),
      ),
    ),
  );
  return OmiConfirmResult(confirmed: confirmed ?? false, dontAskAgain: dontAskAgain);
}

/// Asks to confirm a destructive action in a small menu that pops from [anchor], the on-screen rect
/// of the button that asked (a row's delete button): the consequence ([message]), an optional
/// "Don't ask again" toggle ([offerOptOut]), and the action naming its object ([confirmLabel],
/// "Delete Conversation") in red with [confirmIcon]. Tapping outside cancels.
///
/// The menu lines up with [anchor]'s trailing edge, below it, or above it when there is no room
/// below. At large text sizes, where a 268pt menu has no room, it falls back to the card
/// ([showOmiConfirmWithOptOut] or [showOmiConfirm]) with [title]. Contract as for
/// [showOmiConfirmWithOptOut]: offer the opt-out only when an Undo backs the action.
Future<OmiConfirmResult> showOmiConfirmMenu(
  BuildContext context, {
  required Rect anchor,
  required String title,
  required String message,
  required String confirmLabel,
  Widget? confirmIcon,
  bool offerOptOut = false,
  String? optOutLabel,
}) async {
  if (MediaQuery.textScalerOf(context).scale(1) > _OmiConfirmMenu.maxTextScale) {
    if (offerOptOut) {
      return showOmiConfirmWithOptOut(context,
          title: title, message: message, confirmLabel: confirmLabel, destructive: true, optOutLabel: optOutLabel);
    }
    final confirmed =
        await showOmiConfirm(context, title: title, message: message, confirmLabel: confirmLabel, destructive: true);
    return OmiConfirmResult(confirmed: confirmed, dontAskAgain: false);
  }
  final light = OmiColors.active == OmiPalette.light;
  final screen = MediaQuery.sizeOf(context);
  // Below the button unless it sits in the lower part of the screen; the menu grows from the button.
  final below = anchor.center.dy < screen.height * 0.6;
  final rtl = Directionality.of(context) == TextDirection.rtl;
  final origin = FractionalOffset(
    ((rtl ? anchor.left : anchor.right) / screen.width).clamp(0.0, 1.0),
    ((below ? anchor.bottom : anchor.top) / screen.height).clamp(0.0, 1.0),
  );
  var dontAskAgain = false;
  final confirmed = await showGeneralDialog<bool>(
    context: context,
    barrierDismissible: true,
    barrierLabel: MaterialLocalizations.of(context).modalBarrierDismissLabel,
    barrierColor: Colors.black.withValues(alpha: light ? 0.06 : 0.35),
    transitionDuration: OmiMotion.of(context).standard,
    pageBuilder: (dialogContext, _, __) => CustomSingleChildLayout(
      delegate: _OmiConfirmMenuLayout(
        anchor: anchor,
        below: below,
        padding: MediaQuery.paddingOf(dialogContext),
        textDirection: Directionality.of(dialogContext),
      ),
      child: _OmiConfirmMenu(
        title: title,
        message: message,
        confirmLabel: confirmLabel,
        confirmIcon: confirmIcon,
        optOutLabel: offerOptOut ? (optOutLabel ?? dialogContext.l10n.dontAskAgain) : null,
        onOptOutChanged: (value) => dontAskAgain = value,
        onConfirm: () => Navigator.of(dialogContext).pop(true),
      ),
    ),
    transitionBuilder: (_, animation, __, child) => FadeTransition(
      opacity: CurvedAnimation(parent: animation, curve: const Interval(0, 0.6, curve: Curves.easeOut)),
      child: ScaleTransition(
        scale: Tween<double>(begin: 0.5, end: 1)
            .animate(CurvedAnimation(parent: animation, curve: Curves.easeOutBack, reverseCurve: Curves.easeIn)),
        alignment: origin,
        child: child,
      ),
    ),
  );
  return OmiConfirmResult(confirmed: confirmed ?? false, dontAskAgain: dontAskAgain);
}

/// Places the confirm menu against its anchor: trailing edges lined up, 8pt below (or above), and
/// never closer than 16pt to the screen's edges or the safe area.
class _OmiConfirmMenuLayout extends SingleChildLayoutDelegate {
  _OmiConfirmMenuLayout(
      {required this.anchor, required this.below, required this.padding, required this.textDirection});

  final Rect anchor;
  final bool below;
  final EdgeInsets padding;
  final TextDirection textDirection;

  static const double _margin = OmiSpacing.md;
  static const double _gap = OmiSpacing.xs;

  @override
  BoxConstraints getConstraintsForChild(BoxConstraints constraints) {
    final width = math.min(_OmiConfirmMenu.width, constraints.maxWidth - 2 * _margin);
    return BoxConstraints.tightFor(width: width)
        .copyWith(maxHeight: math.max(0.0, constraints.maxHeight - padding.vertical - 2 * _margin));
  }

  @override
  Offset getPositionForChild(Size size, Size childSize) {
    final double x = (textDirection == TextDirection.rtl ? anchor.left : anchor.right - childSize.width)
        .clamp(_margin, math.max(_margin, size.width - _margin - childSize.width));
    final top = padding.top + _margin;
    final bottom = size.height - padding.bottom - _margin;
    final fitsBelow = anchor.bottom + _gap + childSize.height <= bottom;
    final fitsAbove = anchor.top - _gap - childSize.height >= top;
    final y = (below && fitsBelow) || !fitsAbove ? anchor.bottom + _gap : anchor.top - _gap - childSize.height;
    return Offset(x, y.clamp(top, math.max(top, bottom - childSize.height)).toDouble());
  }

  @override
  bool shouldRelayout(_OmiConfirmMenuLayout oldDelegate) =>
      anchor != oldDelegate.anchor ||
      below != oldDelegate.below ||
      padding != oldDelegate.padding ||
      textDirection != oldDelegate.textDirection;
}

/// The menu [showOmiConfirmMenu] shows: frosted, with the consequence on top, the opt-out toggle,
/// and the destructive action in its own group.
class _OmiConfirmMenu extends StatefulWidget {
  const _OmiConfirmMenu({
    required this.title,
    required this.message,
    required this.confirmLabel,
    required this.confirmIcon,
    required this.optOutLabel,
    required this.onOptOutChanged,
    required this.onConfirm,
  });

  static const double width = 268;

  /// Above this text scale the menu falls back to the card.
  static const double maxTextScale = 1.3;

  final String title;
  final String message;
  final String confirmLabel;
  final Widget? confirmIcon;
  final String? optOutLabel;
  final ValueChanged<bool> onOptOutChanged;
  final VoidCallback onConfirm;

  @override
  State<_OmiConfirmMenu> createState() => _OmiConfirmMenuState();
}

class _OmiConfirmMenuState extends State<_OmiConfirmMenu> {
  bool _optOut = false;

  @override
  Widget build(BuildContext context) {
    final light = OmiColors.active == OmiPalette.light;
    final surface = (light ? OmiColors.surface1 : OmiColors.surface2).withValues(alpha: 0.92);
    final hairline = Divider(height: 1, thickness: 0.5, color: OmiColors.border);
    final optOutLabel = widget.optOutLabel;
    return Semantics(
      scopesRoute: true,
      namesRoute: true,
      explicitChildNodes: true,
      label: widget.title,
      child: DecoratedBox(
        decoration: BoxDecoration(
          borderRadius: OmiRadius.mdAll,
          boxShadow: [
            BoxShadow(color: Colors.black.withValues(alpha: 0.22), blurRadius: 44, offset: const Offset(0, 14))
          ],
        ),
        child: ClipRRect(
          borderRadius: OmiRadius.mdAll,
          child: BackdropFilter(
            filter: ImageFilter.blur(sigmaX: 30, sigmaY: 30),
            child: Material(
              color: surface,
              child: SingleChildScrollView(
                child: Column(
                  mainAxisSize: MainAxisSize.min,
                  crossAxisAlignment: CrossAxisAlignment.stretch,
                  children: [
                    Padding(
                      padding: const EdgeInsets.fromLTRB(OmiSpacing.md, OmiSpacing.sm, OmiSpacing.md, OmiSpacing.sm),
                      child: Text(
                        widget.message,
                        style: OmiType.footnote.copyWith(color: OmiColors.textTertiary, height: 1.35),
                      ),
                    ),
                    if (optOutLabel != null) ...[
                      hairline,
                      _OmiMenuItem(
                        key: const ValueKey('omi_confirm_menu_opt_out'),
                        label: optOutLabel,
                        checked: _optOut,
                        onTap: () {
                          setState(() => _optOut = !_optOut);
                          widget.onOptOutChanged(_optOut);
                        },
                      ),
                    ],
                    // The destructive action sits in its own group, as in an iOS menu.
                    ColoredBox(
                        color: OmiColors.textPrimary.withValues(alpha: 0.07),
                        child: const SizedBox(height: OmiSpacing.xs)),
                    _OmiMenuItem(
                      key: const ValueKey('omi_confirm_menu_confirm'),
                      label: widget.confirmLabel,
                      color: OmiColors.danger,
                      trailing: widget.confirmIcon,
                      onTap: widget.onConfirm,
                    ),
                  ],
                ),
              ),
            ),
          ),
        ),
      ),
    );
  }
}

/// One ≥44pt row of the confirm menu. A [checked] row is a toggle with a leading checkmark.
class _OmiMenuItem extends StatelessWidget {
  const _OmiMenuItem({super.key, required this.label, required this.onTap, this.checked, this.color, this.trailing});

  final String label;
  final VoidCallback onTap;
  final bool? checked;
  final Color? color;
  final Widget? trailing;

  @override
  Widget build(BuildContext context) {
    final ink = color ?? OmiColors.textPrimary;
    final checked = this.checked;
    return Semantics(
      button: checked == null,
      checked: checked,
      child: InkWell(
        onTap: onTap,
        splashFactory: NoSplash.splashFactory,
        highlightColor: OmiColors.textPrimary.withValues(alpha: 0.08),
        child: ConstrainedBox(
          constraints: const BoxConstraints(minHeight: 44),
          child: Padding(
            padding: const EdgeInsets.symmetric(horizontal: OmiSpacing.md, vertical: OmiSpacing.xs),
            child: Row(
              children: [
                if (checked != null) ...[
                  SizedBox(
                    width: 16,
                    child: checked ? Icon(Icons.check_rounded, size: 18, color: ink) : null,
                  ),
                  const SizedBox(width: OmiSpacing.xs),
                ],
                Expanded(child: Text(label, style: OmiType.body.copyWith(color: ink))),
                if (trailing != null) ...[
                  const SizedBox(width: OmiSpacing.xs),
                  IconTheme(data: IconThemeData(size: 17, color: ink), child: trailing!),
                ],
              ],
            ),
          ),
        ),
      ),
    );
  }
}

/// Information with one button ([okLabel], default "OK"). Resolves when it closes.
Future<void> showOmiAlert(
  BuildContext context, {
  required String title,
  String? message,
  String? okLabel,
  bool barrierDismissible = true,
}) {
  return showDialog<void>(
    context: context,
    barrierDismissible: barrierDismissible,
    builder: (dialogContext) => OmiAlertDialog(
      title: title,
      message: message,
      actions: [
        OmiDialogAction(
          label: okLabel ?? dialogContext.l10n.ok,
          isDefault: true,
          onPressed: () => Navigator.of(dialogContext).pop(),
        ),
      ],
    ),
  );
}

List<OmiDialogAction> _confirmActions(
  BuildContext context, {
  required String confirmLabel,
  required String? cancelLabel,
  required bool destructive,
  required VoidCallback onCancel,
  required VoidCallback onConfirm,
}) {
  return [
    OmiDialogAction(label: cancelLabel ?? context.l10n.cancel, isDefault: destructive, onPressed: onCancel),
    OmiDialogAction(label: confirmLabel, isDestructive: destructive, isDefault: !destructive, onPressed: onConfirm),
  ];
}

/// A checkbox with its label as one ≥44pt tappable row (the label toggles it too).
///
/// The box sits right beside its label, drawn in the surrounding text colour so it reads on light
/// and dark surfaces.
class OmiCheckboxRow extends StatelessWidget {
  const OmiCheckboxRow({super.key, required this.label, required this.value, required this.onChanged});

  final String label;
  final bool value;
  final ValueChanged<bool> onChanged;

  @override
  Widget build(BuildContext context) {
    final ink = DefaultTextStyle.of(context).style.color ?? OmiColors.textPrimary;
    return MergeSemantics(
      child: Semantics(
        checked: value,
        // GestureDetector, not InkWell: CupertinoAlertDialog has no Material ancestor.
        child: GestureDetector(
          behavior: HitTestBehavior.opaque,
          onTap: () => onChanged(!value),
          // At least 44pt tall (a wrapped label at a large text size grows it).
          child: ConstrainedBox(
            constraints: const BoxConstraints(minHeight: 44),
            child: Row(
              mainAxisSize: MainAxisSize.min,
              children: [
                ExcludeSemantics(
                  child: _OmiCheckBox(value: value, ink: ink),
                ),
                const SizedBox(width: OmiSpacing.xs),
                Flexible(child: Text(label, textAlign: TextAlign.start)),
              ],
            ),
          ),
        ),
      ),
    );
  }
}

/// The 18pt rounded box of [OmiCheckboxRow]: an outline in [ink] when off, filled with a check
/// when on.
class _OmiCheckBox extends StatelessWidget {
  const _OmiCheckBox({required this.value, required this.ink});

  final bool value;
  final Color ink;

  @override
  Widget build(BuildContext context) {
    // The check takes whichever of black or white stands out on the filled box.
    final check = ink.computeLuminance() > 0.5 ? Colors.black : Colors.white;
    return AnimatedContainer(
      key: const ValueKey('omi_checkbox_box'),
      duration: OmiMotion.of(context).quick,
      width: 18,
      height: 18,
      decoration: BoxDecoration(
        color: value ? ink : Colors.transparent,
        borderRadius: const BorderRadius.all(Radius.circular(5)),
        border: Border.all(color: value ? ink : ink.withValues(alpha: 0.45), width: 1.5),
      ),
      child: value ? Icon(Icons.check_rounded, size: 14, color: check) : null,
    );
  }
}

/// A dialog that holds a control (the "Don't ask again" row): Omi's own card, on every platform.
///
/// Its width follows the screen, 32pt in from each side and at most 400pt. Title, message and
/// [content] are centred, like the system alerts beside it, and scroll at large text sizes. The buttons are plain text in a bar
/// along the bottom, split by hairlines like an iOS alert: a destructive action red, the default
/// choice bold. Two buttons sit side by side and stack, the action on top, when a label would not
/// fit.
class OmiDialogCard extends StatelessWidget {
  const OmiDialogCard({super.key, required this.title, this.message, this.content, required this.actions});

  final String title;
  final String? message;

  /// A control under [message], such as an [OmiCheckboxRow].
  final Widget? content;
  final List<OmiDialogAction> actions;

  static const double maxWidth = 400;

  @override
  Widget build(BuildContext context) {
    return Dialog(
      backgroundColor: OmiColors.surface1,
      surfaceTintColor: Colors.transparent,
      insetPadding: const EdgeInsets.symmetric(horizontal: OmiSpacing.xxl, vertical: OmiSpacing.xl),
      shape: const RoundedRectangleBorder(borderRadius: OmiRadius.lgAll),
      clipBehavior: Clip.antiAlias,
      child: ConstrainedBox(
        constraints: const BoxConstraints(maxWidth: maxWidth),
        child: Semantics(
          scopesRoute: true,
          namesRoute: true,
          explicitChildNodes: true,
          label: title,
          child: Column(
            mainAxisSize: MainAxisSize.min,
            crossAxisAlignment: CrossAxisAlignment.stretch,
            children: [
              Flexible(
                child: SingleChildScrollView(
                  padding: EdgeInsets.fromLTRB(
                    OmiSpacing.lg,
                    OmiSpacing.lg,
                    OmiSpacing.lg,
                    // The 44pt row already carries air under its box.
                    content != null ? OmiSpacing.xs : OmiSpacing.lg,
                  ),
                  child: Column(
                    children: [
                      Text(title, style: OmiType.headline, textAlign: TextAlign.center),
                      if (message != null) ...[
                        const SizedBox(height: OmiSpacing.xxs),
                        // Not textSecondary: in light mode that is 60% ink, about 3.5:1 on white.
                        // Tertiary keeps the message at 4.5:1 or better in both modes.
                        Text(
                          message!,
                          style: OmiType.subhead.copyWith(color: OmiColors.textTertiary, height: 1.35),
                          textAlign: TextAlign.center,
                        ),
                      ],
                      if (content != null) ...[
                        const SizedBox(height: OmiSpacing.xxs),
                        DefaultTextStyle(style: OmiType.subhead, child: content!),
                      ],
                    ],
                  ),
                ),
              ),
              _OmiDialogCardButtons(actions: actions),
            ],
          ),
        ),
      ),
    );
  }
}

class _OmiDialogCardButtons extends StatelessWidget {
  const _OmiDialogCardButtons({required this.actions});

  final List<OmiDialogAction> actions;

  static const double _height = 50;
  static const double _sidePadding = OmiSpacing.md;

  TextStyle _style(OmiDialogAction action) => OmiType.body.copyWith(
        color: action.isDestructive ? OmiColors.danger : OmiColors.textPrimary,
        fontWeight: action.isDefault ? FontWeight.w600 : FontWeight.w400,
      );

  Widget _button(OmiDialogAction action) {
    final style = _style(action);
    return TextButton(
      key: action.key,
      onPressed: action.onPressed,
      style: TextButton.styleFrom(
        foregroundColor: style.color,
        minimumSize: const Size.fromHeight(_height),
        padding: const EdgeInsets.symmetric(horizontal: _sidePadding),
        shape: const RoundedRectangleBorder(),
        tapTargetSize: MaterialTapTargetSize.shrinkWrap,
        textStyle: style,
      ),
      child: Text(action.label, style: style, maxLines: 1, overflow: TextOverflow.ellipsis),
    );
  }

  @override
  Widget build(BuildContext context) {
    final hairline = Divider(height: 1, thickness: 0.5, color: OmiColors.border);
    return LayoutBuilder(builder: (context, constraints) {
      final half = constraints.maxWidth / 2;
      final textScaler = MediaQuery.textScalerOf(context);
      final textDirection = Directionality.of(context);
      // A label fits when it and the button's side padding fit in half the bar.
      bool fits(OmiDialogAction action) {
        final painter = TextPainter(
          text: TextSpan(text: action.label, style: _style(action)),
          textDirection: textDirection,
          textScaler: textScaler,
          maxLines: 1,
        )..layout();
        final width = painter.width + 2 * _sidePadding;
        painter.dispose();
        return width <= half;
      }

      if (actions.length == 2 && actions.every(fits)) {
        return Column(
          mainAxisSize: MainAxisSize.min,
          crossAxisAlignment: CrossAxisAlignment.stretch,
          children: [
            hairline,
            IntrinsicHeight(
              child: Row(
                crossAxisAlignment: CrossAxisAlignment.stretch,
                children: [
                  Expanded(child: _button(actions.first)),
                  VerticalDivider(width: 1, thickness: 0.5, color: OmiColors.border),
                  Expanded(child: _button(actions.last)),
                ],
              ),
            ),
          ],
        );
      }
      // Stacked: the action on top, Cancel last, the way iOS stacks an alert's buttons.
      return Column(
        mainAxisSize: MainAxisSize.min,
        crossAxisAlignment: CrossAxisAlignment.stretch,
        children: [
          for (final action in actions.reversed) ...[hairline, _button(action)],
        ],
      );
    });
  }
}
