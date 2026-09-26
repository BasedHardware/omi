import 'package:flutter/material.dart';

import 'package:omi/ui/components/omi_nav_buttons.dart';
import 'package:omi/ui/omi_tokens.dart';

/// Shows a modal bottom sheet in the app's one sheet shell and returns its result.
///
/// The shell: [OmiColors.surface1] with 24pt top corners, the framework drag handle (36x4, which
/// screen readers can activate to dismiss), an optional title row with a trailing
/// [OmiCloseButton], bottom safe-area padding, and padding for the keyboard so text fields stay
/// visible. Content that does not fit scrolls if it is (or contains) a scrollable; wrap a long
/// `Column` in a `SingleChildScrollView`.
///
/// ```dart
/// final folder = await showOmiSheet<Folder>(
///   context: context,
///   title: l10n.moveToFolder,
///   builder: (context) => FolderPicker(...),
/// );
/// ```
///
/// Migrating an existing sheet: delete its hand-drawn handle, title row and close X, and pass its
/// title here. Sheets are dismissed by the X, a swipe down, or a tap on the scrim; set
/// [isDismissible]/[enableDrag] to false only while an irreversible operation runs.
Future<T?> showOmiSheet<T>({
  required BuildContext context,
  required WidgetBuilder builder,
  String? title,
  bool showCloseButton = true,
  bool isScrollControlled = true,
  bool useSafeArea = true,
  bool isDismissible = true,
  bool enableDrag = true,
  bool useRootNavigator = false,
  EdgeInsetsGeometry padding = const EdgeInsets.symmetric(horizontal: OmiSpacing.md),
  RouteSettings? routeSettings,
}) {
  return showModalBottomSheet<T>(
    context: context,
    isScrollControlled: isScrollControlled,
    useSafeArea: useSafeArea,
    isDismissible: isDismissible,
    enableDrag: enableDrag,
    useRootNavigator: useRootNavigator,
    routeSettings: routeSettings,
    // Size (36x4) and colour come from the app theme's bottomSheetTheme (buildOmiTheme).
    showDragHandle: true,
    backgroundColor: OmiColors.surface1,
    shape: const RoundedRectangleBorder(borderRadius: OmiRadius.sheetTop),
    clipBehavior: Clip.antiAlias,
    builder: (sheetContext) => OmiSheetScaffold(
      title: title,
      showCloseButton: showCloseButton,
      padding: padding,
      child: Builder(builder: builder),
    ),
  );
}

/// The inside of an Omi sheet: optional title row with a trailing close X, the content, and the
/// bottom safe-area and keyboard insets.
///
/// [showOmiSheet] wraps its builder in this already. Use it directly only when a sheet must be
/// presented some other way (a `DraggableScrollableSheet`, a nested navigator) but should look
/// the same.
class OmiSheetScaffold extends StatelessWidget {
  const OmiSheetScaffold({
    super.key,
    required this.child,
    this.title,
    this.showCloseButton = true,
    this.onClose,
    this.padding = const EdgeInsets.symmetric(horizontal: OmiSpacing.md),
  });

  final Widget child;

  /// Sheet title (Title Case). Without a title and without a close button, no header is drawn.
  final String? title;

  final bool showCloseButton;

  /// Close action; defaults to popping the sheet.
  final VoidCallback? onClose;

  /// Padding around [child].
  final EdgeInsetsGeometry padding;

  @override
  Widget build(BuildContext context) {
    final hasHeader = title != null || showCloseButton;
    final keyboard = MediaQuery.viewInsetsOf(context).bottom;
    return Padding(
      padding: EdgeInsets.only(bottom: keyboard),
      child: SafeArea(
        top: false,
        child: Column(
          mainAxisSize: MainAxisSize.min,
          crossAxisAlignment: CrossAxisAlignment.stretch,
          children: [
            if (hasHeader)
              Padding(
                padding: const EdgeInsetsDirectional.only(start: OmiSpacing.md, end: OmiSpacing.xxs),
                child: Row(
                  children: [
                    Expanded(
                      child: title == null
                          ? const SizedBox.shrink()
                          : Semantics(
                              header: true,
                              child:
                                  Text(title!, style: OmiType.headline, maxLines: 2, overflow: TextOverflow.ellipsis),
                            ),
                    ),
                    if (showCloseButton) OmiCloseButton(onPressed: onClose, color: OmiColors.textSecondary),
                  ],
                ),
              ),
            Flexible(child: Padding(padding: padding, child: child)),
          ],
        ),
      ),
    );
  }
}
