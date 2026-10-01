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
