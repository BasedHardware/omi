import 'package:flutter/material.dart';
import 'package:flutter/services.dart';

import 'package:omi/ui/components/omi_nav_buttons.dart';
import 'package:omi/ui/omi_appearance.dart';
import 'package:omi/ui/omi_tokens.dart';

/// The v2 header of a pushed page: the round back button and any actions on one row, then the
/// page title as a 34pt large title under it (iOS large-title layout, on both platforms).
///
/// A drop-in for `AppBar(leading:, title:, actions:, bottom:)`:
///
/// ```dart
/// Scaffold(appBar: OmiAppBar(leading: const OmiBackButton(), title: Text(l10n.notifications)))
/// ```
///
/// With no [leading], a page that can pop gets [OmiBackButton]. A [title] with its own style keeps
/// it; a plain `Text` takes [OmiType.largeTitle] and shrinks to fit rather than wrapping.
/// [inlineTitle] is the compact alternative: a 17pt title centred on the button row (the sheet
/// header of a device page), with no large title under it.
class OmiAppBar extends StatelessWidget implements PreferredSizeWidget {
  const OmiAppBar({
    super.key,
    this.leading,
    this.automaticallyImplyLeading = true,
    this.title,
    this.inlineTitle,
    this.actions,
    this.bottom,
    this.backgroundColor,
  });

  final Widget? leading;
  final bool automaticallyImplyLeading;
  final Widget? title;
  final Widget? inlineTitle;
  final List<Widget>? actions;

  /// Under the title, e.g. a `TabBar`.
  final PreferredSizeWidget? bottom;

  /// Defaults to the page colour.
  final Color? backgroundColor;

  static const double _toolbarHeight = kToolbarHeight;
  static const double _titleHeight = 48;

  @override
  Size get preferredSize => Size.fromHeight(
        _toolbarHeight + (title != null ? _titleHeight : 0) + (bottom?.preferredSize.height ?? 0),
      );

  @override
  Widget build(BuildContext context) {
    final canPop = ModalRoute.of(context)?.canPop ?? false;
    final lead = leading ?? (automaticallyImplyLeading && canPop ? const OmiBackButton() : null);
    return AnnotatedRegion<SystemUiOverlayStyle>(
      // Status bar icons that read on this palette's page (dark icons in light mode).
      value: OmiAppearance.overlayFor(OmiColors.palette),
      child: Material(
        color: backgroundColor ?? OmiColors.surface0,
        child: SafeArea(
          bottom: false,
          child: Column(
            mainAxisSize: MainAxisSize.min,
            crossAxisAlignment: CrossAxisAlignment.stretch,
            children: [
              SizedBox(
                height: _toolbarHeight,
                child: Padding(
                  padding: const EdgeInsets.symmetric(horizontal: OmiSpacing.sm),
                  child: IconTheme.merge(
                    data: IconThemeData(color: OmiColors.textPrimary),
                    child: Stack(
                      alignment: Alignment.center,
                      children: [
                        if (inlineTitle != null)
                          // Clear of a 44pt button on each side.
                          Padding(
                            padding: const EdgeInsets.symmetric(horizontal: 56),
                            child: Semantics(
                              header: true,
                              child: DefaultTextStyle.merge(
                                style: OmiType.headline,
                                maxLines: 1,
                                overflow: TextOverflow.ellipsis,
                                textAlign: TextAlign.center,
                                child: inlineTitle!,
                              ),
                            ),
                          ),
                        Row(
                          children: [
                            if (lead != null) lead,
                            const Spacer(),
                            ...?actions,
                          ],
                        ),
                      ],
                    ),
                  ),
                ),
              ),
              if (title != null)
                SizedBox(
                  height: _titleHeight,
                  child: Padding(
                    padding: const EdgeInsets.symmetric(horizontal: OmiSize.screenMargin),
                    child: Align(
                      alignment: AlignmentDirectional.centerStart,
                      child: Semantics(
                        header: true,
                        child: DefaultTextStyle.merge(
                          style: OmiType.largeTitle,
                          maxLines: 1,
                          child: FittedBox(
                            fit: BoxFit.scaleDown,
                            alignment: AlignmentDirectional.centerStart,
                            child: title!,
                          ),
                        ),
                      ),
                    ),
                  ),
                ),
              if (bottom != null) bottom!,
            ],
          ),
        ),
      ),
    );
  }
}
