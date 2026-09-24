import 'dart:async';

import 'package:flutter/material.dart';

import 'package:omi/ui/components/omi_button.dart';
import 'package:omi/ui/components/omi_spinner.dart';
import 'package:omi/ui/omi_tokens.dart';
import 'package:omi/utils/l10n_extensions.dart';

// A page body (or a section of one) that has no rows yet is in exactly one of three states,
// each with one component: first load [OmiLoadingState], load failed [OmiErrorState], nothing
// here / nothing matches [OmiEmptyState]. Do not hand-draw an icon-title-button stack.
//
// Each state centres itself in the space it is given. Inside a scroll view (for example under a
// `RefreshIndicator`) give it a height, e.g. wrap it in `SliverFillRemaining(hasScrollBody: false)`.

/// First load of a page or section: one regular spinner, optionally with a label
/// ("Loading tasks…").
class OmiLoadingState extends StatelessWidget {
  const OmiLoadingState({super.key, this.label});

  final String? label;

  @override
  Widget build(BuildContext context) {
    return Center(
      child: Padding(
        padding: const EdgeInsets.all(OmiSpacing.xl),
        child: OmiSpinner(label: label),
      ),
    );
  }
}

/// Nothing here yet, or nothing matches the search/filter.
///
/// Title is Title Case ("No Tasks Yet", "No Matching Memories"); [message] says what to do next.
/// [action] is usually a compact secondary [OmiButton] ("Clear Search"), or one compact primary
/// when the action is how the page gets its first row ("New Memory").
///
/// The glyph is either a Material [icon] or any [glyph] widget — for example
/// `FaIcon(FontAwesomeIcons.key)` when the screen's other controls use FontAwesome. Exactly one of
/// the two is given; either way it is drawn 40pt in [OmiColors.textTertiary].
class OmiEmptyState extends StatelessWidget {
  const OmiEmptyState({super.key, this.icon, this.glyph, required this.title, this.message, this.action})
      : assert((icon == null) != (glyph == null), 'Give OmiEmptyState exactly one of icon or glyph');

  final IconData? icon;

  /// A glyph that is not a Material [IconData], sized and coloured through [IconTheme].
  final Widget? glyph;

  final String title;
  final String? message;
  final Widget? action;

  @override
  Widget build(BuildContext context) {
    return _StateLayout(glyph: glyph ?? Icon(icon), title: title, message: message, action: action);
  }
}

/// A load failed. Shows what went wrong and a **Try Again** button (compact, secondary).
///
/// [message] is the reader-facing reason; [title] is optional ("Couldn't Load Tasks"). When
/// [onRetry] returns a [Future] the button spins until it completes. Without [onRetry] no button
/// is drawn — only do that when retrying is impossible.
class OmiErrorState extends StatelessWidget {
  const OmiErrorState({super.key, required this.message, this.onRetry, this.title, this.retryLabel});

  final String message;
  final String? title;
  final FutureOr<void> Function()? onRetry;

  /// Defaults to the localized "Try Again".
  final String? retryLabel;

  @override
  Widget build(BuildContext context) {
    return _StateLayout(
      glyph: const Icon(Icons.error_outline),
      title: title,
      message: message,
      action: onRetry == null
          ? null
          : OmiButton.secondary(
              label: retryLabel ?? context.l10n.tryAgain,
              onPressed: onRetry,
              size: OmiButtonSize.compact,
            ),
    );
  }
}

class _StateLayout extends StatelessWidget {
  const _StateLayout({required this.glyph, this.title, this.message, this.action});

  final Widget glyph;
  final String? title;
  final String? message;
  final Widget? action;

  @override
  Widget build(BuildContext context) {
    return Center(
      child: Padding(
        padding: const EdgeInsets.symmetric(horizontal: OmiSpacing.xxl, vertical: OmiSpacing.xl),
        child: Column(
          mainAxisSize: MainAxisSize.min,
          children: [
            ExcludeSemantics(
              child: IconTheme.merge(
                data: const IconThemeData(size: 40, color: OmiColors.textTertiary),
                child: glyph,
              ),
            ),
            if (title != null) ...[
              const SizedBox(height: OmiSpacing.md),
              Semantics(
                header: true,
                child: Text(title!, textAlign: TextAlign.center, style: OmiType.headline),
              ),
            ],
            if (message != null) ...[
              SizedBox(height: title != null ? OmiSpacing.xs : OmiSpacing.md),
              Text(
                message!,
                textAlign: TextAlign.center,
                style: OmiType.subhead.copyWith(color: OmiColors.textSecondary),
              ),
            ],
            if (action != null) ...[
              const SizedBox(height: OmiSpacing.lg),
              action!,
            ],
          ],
        ),
      ),
    );
  }
}
