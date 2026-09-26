import 'package:flutter/material.dart';

import 'package:omi/ui/components/omi_nav_buttons.dart';
import 'package:omi/ui/feedback/omi_dialogs.dart';
import 'package:omi/ui/omi_tokens.dart';
import 'package:omi/utils/l10n_extensions.dart';

/// Presents a sheet that **edits** something (docs/ux-contract.md §2) and returns its result.
///
/// Use it with an [OmiEditSheet] as the builder's root. The sheet can be left by its close X, a
/// swipe down, a tap on the scrim or system back; while the editor reports [OmiEditSheet.isDirty]
/// every one of those asks "Discard changes?" first. Save/Cancel inside the sheet pop it directly.
///
/// ```dart
/// await showOmiEditSheet<void>(
///   context: context,
///   builder: (_) => const ActionItemFormSheet(),
/// );
/// ```
///
/// Why not [showOmiSheet]: the framework's drag-to-dismiss pops the route without asking the
/// page, so an editing sheet owns its drag (in [OmiEditSheet]) and routes it through
/// `Navigator.maybePop`, which the dirty guard can refuse.
Future<T?> showOmiEditSheet<T>({
  required BuildContext context,
  required WidgetBuilder builder,
  bool useRootNavigator = false,
  RouteSettings? routeSettings,
}) {
  return showModalBottomSheet<T>(
    context: context,
    isScrollControlled: true,
    useSafeArea: true,
    useRootNavigator: useRootNavigator,
    routeSettings: routeSettings,
    // The sheet draws its own surface, handle and drag (see OmiEditSheet).
    backgroundColor: Colors.transparent,
    enableDrag: false,
    showDragHandle: false,
    builder: builder,
  );
}

/// Asks "Discard changes?" with Discard (destructive) and Keep Editing. Resolves `true` when the
/// reader chose Discard.
Future<bool> confirmDiscardChanges(BuildContext context) {
  final l10n = context.l10n;
  return showOmiConfirm(
    context,
    title: l10n.discardChangesTitle,
    message: l10n.discardChangesMessage,
    confirmLabel: l10n.discard,
    cancelLabel: l10n.keepEditing,
    destructive: true,
  );
}

/// The shell of an editing sheet: surface, drag handle, title row with [actions] and a trailing
/// close X, keyboard and safe-area insets — plus the dirty guard.
///
/// While [isDirty] is true, system back, a tap on the scrim, the close X and a swipe down all ask
/// [confirmDiscardChanges] before the sheet closes. A clean sheet just closes. Save and Cancel
/// buttons inside [child] call `Navigator.pop` directly, which is never guarded.
///
/// It paints its own surface, so it also works under a plain transparent `showModalBottomSheet`
/// (the guard and the swipe then still apply to the content); prefer [showOmiEditSheet].
class OmiEditSheet extends StatefulWidget {
  const OmiEditSheet({
    super.key,
    required this.child,
    required this.isDirty,
    this.title,
    this.actions = const [],
    this.enabled = true,
    this.padding = const EdgeInsets.fromLTRB(OmiSpacing.md, 0, OmiSpacing.md, OmiSpacing.md),
  });

  final Widget child;

  /// Whether leaving now would lose edits.
  final bool isDirty;

  /// Sheet title (Title Case): "Edit Task", "New Memory".
  final String? title;

  /// Icon controls placed before the close X (share, delete): usually [OmiIconButton]s.
  final List<Widget> actions;

  /// False while a save is in flight: the X and the swipe do nothing.
  final bool enabled;

  final EdgeInsetsGeometry padding;

  @override
  State<OmiEditSheet> createState() => _OmiEditSheetState();
}

class _OmiEditSheetState extends State<OmiEditSheet> {
  /// How far the sheet has been dragged down, in logical pixels.
  final ValueNotifier<double> _dragOffset = ValueNotifier<double>(0);
  bool _asking = false;

  static const double _dismissDistance = 96;
  static const double _dismissVelocity = 700;

  @override
  void dispose() {
    _dragOffset.dispose();
    super.dispose();
  }

  Future<void> _onPopBlocked() async {
    if (_asking || !mounted) return;
    _asking = true;
    final discard = await confirmDiscardChanges(context);
    _asking = false;
    if (discard && mounted) Navigator.of(context).pop();
  }

  void _requestClose() {
    if (!widget.enabled) return;
    // maybePop consults the PopScope below, so a dirty sheet asks first.
    Navigator.maybePop(context);
  }

  void _onDragUpdate(DragUpdateDetails details) {
    if (!widget.enabled) return;
    _dragOffset.value = (_dragOffset.value + details.delta.dy).clamp(0.0, double.infinity);
  }

  void _onDragEnd(DragEndDetails details) {
    final shouldClose = _dragOffset.value > _dismissDistance || details.velocity.pixelsPerSecond.dy > _dismissVelocity;
    _dragOffset.value = 0;
    if (shouldClose) _requestClose();
  }

  @override
  Widget build(BuildContext context) {
    final keyboard = MediaQuery.viewInsetsOf(context).bottom;
    return PopScope<Object?>(
      canPop: !widget.isDirty,
      onPopInvokedWithResult: (didPop, _) {
        if (!didPop) _onPopBlocked();
      },
      child: Padding(
        padding: EdgeInsets.only(bottom: keyboard),
        child: ValueListenableBuilder<double>(
          valueListenable: _dragOffset,
          builder: (context, offset, child) => Transform.translate(offset: Offset(0, offset), child: child),
          child: Material(
            color: OmiColors.surface1,
            shape: const RoundedRectangleBorder(borderRadius: OmiRadius.sheetTop),
            clipBehavior: Clip.antiAlias,
            child: SafeArea(
              top: false,
              // The whole sheet drags down; scrollables and text fields inside keep their own
              // gestures because the innermost recognizer wins.
              child: GestureDetector(
                behavior: HitTestBehavior.translucent,
                onVerticalDragUpdate: _onDragUpdate,
                onVerticalDragEnd: _onDragEnd,
                child: Column(
                  mainAxisSize: MainAxisSize.min,
                  crossAxisAlignment: CrossAxisAlignment.stretch,
                  children: [
                    Semantics(
                      button: true,
                      label: MaterialLocalizations.of(context).modalBarrierDismissLabel,
                      onTap: _requestClose,
                      child: SizedBox(
                        height: 20,
                        child: Center(
                          child: Container(
                            width: 36,
                            height: 4,
                            decoration: const BoxDecoration(color: OmiColors.border, borderRadius: OmiRadius.pillAll),
                          ),
                        ),
                      ),
                    ),
                    Padding(
                      padding: const EdgeInsetsDirectional.only(start: OmiSpacing.md, end: OmiSpacing.xxs),
                      child: Row(
                        children: [
                          Expanded(
                            child: widget.title != null
                                ? Semantics(
                                    header: true,
                                    child: Text(
                                      widget.title!,
                                      style: OmiType.headline,
                                      maxLines: 2,
                                      overflow: TextOverflow.ellipsis,
                                    ),
                                  )
                                : const SizedBox.shrink(),
                          ),
                          ...widget.actions,
                          OmiCloseButton(
                            onPressed: _requestClose,
                            color: OmiColors.textSecondary,
                          ),
                        ],
                      ),
                    ),
                    Flexible(child: Padding(padding: widget.padding, child: widget.child)),
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
