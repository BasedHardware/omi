import 'package:flutter/material.dart';

import 'package:omi/ui/components/omi_nav_buttons.dart';
import 'package:omi/ui/components/omi_settings.dart';
import 'package:omi/ui/omi_tokens.dart';

/// A page inside Settings, drawn like Settings itself: [OmiColors.groupedPage] under a circled
/// back button and a centred title, with optional trailing [actions]. Every [OmiSettingsGroup] in
/// [body] is an outlined card and every [OmiSectionHeader] the small label above one
/// ([OmiGroupedScope]).
///
/// ```dart
/// OmiGroupedPage(
///   title: l10n.language,
///   body: ListView(padding: OmiGroupedPage.padding, children: [OmiSettingsGroup(children: rows)]),
/// )
/// ```
class OmiGroupedPage extends StatelessWidget {
  const OmiGroupedPage({
    super.key,
    this.title,
    this.titleWidget,
    this.actions = const [],
    this.onBack,
    this.leading,
    this.bottom,
    required this.body,
    this.bottomNavigationBar,
    this.floatingActionButton,
    this.resizeToAvoidBottomInset,
  });

  /// List padding that lines content up with the Settings page.
  static const padding = EdgeInsets.fromLTRB(OmiSpacing.md, OmiSpacing.sm, OmiSpacing.md, OmiSpacing.xxl);

  final String? title;

  /// Replaces [title] (a step indicator, a selection count).
  final Widget? titleWidget;

  /// Trailing header controls, e.g. [OmiIconButton.filled] with `fillColor: OmiColors.iconTile`.
  final List<Widget> actions;

  /// Back override; defaults to popping the route.
  final VoidCallback? onBack;

  /// Replaces the back button (a selection mode's close).
  final Widget? leading;

  /// A control pinned under the header (period tabs).
  final PreferredSizeWidget? bottom;

  final Widget body;
  final Widget? bottomNavigationBar;
  final Widget? floatingActionButton;
  final bool? resizeToAvoidBottomInset;

  @override
  Widget build(BuildContext context) {
    return OmiSettingsTypeface(
      child: OmiGroupedScope(
        child: Scaffold(
          backgroundColor: OmiColors.groupedPage,
          resizeToAvoidBottomInset: resizeToAvoidBottomInset,
          appBar: AppBar(
            backgroundColor: OmiColors.groupedPage,
            surfaceTintColor: Colors.transparent,
            scrolledUnderElevation: 0,
            elevation: 0,
            toolbarHeight: 52,
            automaticallyImplyLeading: false,
            leadingWidth: 44 + OmiSpacing.xxs,
            leading: Padding(
              padding: const EdgeInsets.only(left: OmiSpacing.xxs),
              child: leading ?? OmiBackButton.circled(fillColor: OmiColors.iconTile, onPressed: onBack),
            ),
            centerTitle: true,
            title: titleWidget ??
                (title == null
                    ? null
                    : Text(title!, style: OmiType.headline, maxLines: 1, overflow: TextOverflow.ellipsis)),
            // Centred, so a text action keeps its own height instead of stretching to the bar's.
            actions: [for (final action in actions) Center(child: action), const SizedBox(width: OmiSpacing.xxs)],
            bottom: bottom,
          ),
          body: body,
          bottomNavigationBar: bottomNavigationBar,
          floatingActionButton: floatingActionButton,
        ),
      ),
    );
  }
}
