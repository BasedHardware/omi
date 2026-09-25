import 'dart:async';

import 'package:flutter/material.dart';

import 'package:omi/ui/components/omi_spinner.dart';
import 'package:omi/ui/omi_tokens.dart';

/// What a button does, which decides how loud it is.
enum OmiButtonVariant {
  /// The one main action on a screen or sheet: white fill, black label.
  primary,

  /// Other actions next to a primary, or the only action on a quiet surface (empty/error states).
  secondary,

  /// Deletes, disconnects, signs out of something that cannot be undone: red label on a red tint.
  destructive,

  /// Low-emphasis text action ("Skip", "Learn More", a dialog's Cancel): no fill.
  tertiary,

  /// A labelled action inside a row of [OmiIconButton.filled] circles (a page header): the same
  /// surface-1 fill and primary-text label and glyph, so the row reads as one calm set.
  toolbar,
}

/// Button heights. Both keep a touch target of at least 44pt.
enum OmiButtonSize {
  /// 48pt tall: page and sheet actions.
  regular,

  /// 36pt visual inside a 48pt touch target: rows, cards, empty/error states, headers.
  compact,
}

/// Explicit colours for a legacy call site whose look is not yet a variant.
///
/// Migration escape hatch only (it served the retired `AnimatedLoadingButton`). New code picks a
/// [OmiButtonVariant].
@immutable
class OmiButtonColors {
  const OmiButtonColors({required this.background, required this.foreground});

  final Color background;
  final Color foreground;
}

/// The app's text button.
///
/// ```dart
/// OmiButton(label: l10n.save, onPressed: _save)                       // primary, 48pt
/// OmiButton.secondary(label: l10n.tryAgain, onPressed: _retry, size: OmiButtonSize.compact)
/// OmiButton.destructive(label: l10n.deleteAccount, onPressed: _confirmDelete, expand: true)
/// OmiButton.tertiary(label: l10n.skip, onPressed: _skip)
/// ```
///
/// When [onPressed] returns a [Future], the button shows a spinner and ignores taps until it
/// completes — also when it throws: the error is reported through [FlutterError.reportError] and
/// the button becomes tappable again. Pass [isLoading] to drive the spinner from outside.
/// A null [onPressed] disables the button.
///
/// Labels are Title Case verbs ("Save", "Try Again", "Delete Conversation").
class OmiButton extends StatefulWidget {
  const OmiButton({
    super.key,
    required this.label,
    required this.onPressed,
    this.variant = OmiButtonVariant.primary,
    this.size = OmiButtonSize.regular,
    this.icon,
    this.leading,
    this.isLoading = false,
    this.expand = false,
    this.colors,
    this.width,
    this.height,
    this.labelStyle,
  });

  const OmiButton.secondary({
    super.key,
    required this.label,
    required this.onPressed,
    this.size = OmiButtonSize.regular,
    this.icon,
    this.leading,
    this.isLoading = false,
    this.expand = false,
  })  : variant = OmiButtonVariant.secondary,
        colors = null,
        width = null,
        height = null,
        labelStyle = null;

  const OmiButton.destructive({
    super.key,
    required this.label,
    required this.onPressed,
    this.size = OmiButtonSize.regular,
    this.icon,
    this.leading,
    this.isLoading = false,
    this.expand = false,
  })  : variant = OmiButtonVariant.destructive,
        colors = null,
        width = null,
        height = null,
        labelStyle = null;

  const OmiButton.tertiary({
    super.key,
    required this.label,
    required this.onPressed,
    this.size = OmiButtonSize.regular,
    this.icon,
    this.leading,
    this.isLoading = false,
    this.expand = false,
  })  : variant = OmiButtonVariant.tertiary,
        colors = null,
        width = null,
        height = null,
        labelStyle = null;

  /// See [OmiButtonVariant.toolbar].
  const OmiButton.toolbar({
    super.key,
    required this.label,
    required this.onPressed,
    this.size = OmiButtonSize.regular,
    this.icon,
    this.leading,
    this.isLoading = false,
    this.expand = false,
  })  : variant = OmiButtonVariant.toolbar,
        colors = null,
        width = null,
        height = null,
        labelStyle = null;

  final String label;

  /// Tap handler. May return a [Future]; the button shows a spinner until it completes.
  final FutureOr<void> Function()? onPressed;

  final OmiButtonVariant variant;
  final OmiButtonSize size;

  /// Optional leading icon from [Icons].
  final IconData? icon;

  /// Optional leading icon widget, for glyphs that are not a Material [IconData] — for example
  /// `FaIcon(FontAwesomeIcons.comments)` so a button can use the same glyph as the tab bar. It is
  /// sized and coloured like [icon] through [IconTheme]. Takes precedence over [icon].
  final Widget? leading;

  /// Shows the spinner and ignores taps, independent of [onPressed]'s future.
  final bool isLoading;

  /// Fill the available width.
  final bool expand;

  /// Legacy colour override; see [OmiButtonColors]. Wins over [variant].
  final OmiButtonColors? colors;

  /// Legacy fixed width. Prefer [expand] or intrinsic width.
  final double? width;

  /// Legacy visual height. The touch target never shrinks below 44pt.
  final double? height;

  /// Legacy label style. Its colour is ignored; the foreground colour always wins.
  final TextStyle? labelStyle;

  @override
  State<OmiButton> createState() => _OmiButtonState();
}

class _OmiButtonState extends State<OmiButton> {
  bool _running = false;

  bool get _loading => widget.isLoading || _running;

  Future<void> _handlePressed() async {
    if (_loading) return;
    final FutureOr<void> result;
    try {
      result = widget.onPressed!();
    } catch (error, stack) {
      _report(error, stack);
      return;
    }
    if (result is! Future) return;
    setState(() => _running = true);
    try {
      await result;
    } catch (error, stack) {
      _report(error, stack);
    } finally {
      if (mounted) setState(() => _running = false);
    }
  }

  void _report(Object error, StackTrace stack) {
    FlutterError.reportError(FlutterErrorDetails(
      exception: error,
      stack: stack,
      library: 'omi ui',
      context: ErrorDescription('while running OmiButton "${widget.label}" onPressed'),
    ));
  }

  ({Color background, Color foreground}) _colors(bool enabled) {
    final override = widget.colors;
    if (override != null) return (background: override.background, foreground: override.foreground);
    if (!enabled) {
      return switch (widget.variant) {
        OmiButtonVariant.tertiary => (background: Colors.transparent, foreground: OmiColors.textDisabled),
        _ => (background: OmiColors.surface2, foreground: OmiColors.textDisabled),
      };
    }
    return switch (widget.variant) {
      OmiButtonVariant.primary => (background: OmiColors.accent, foreground: OmiColors.onAccent),
      OmiButtonVariant.secondary => (background: OmiColors.surface2, foreground: OmiColors.textPrimary),
      OmiButtonVariant.destructive => (background: OmiColors.dangerSurface, foreground: OmiColors.danger),
      OmiButtonVariant.tertiary => (background: Colors.transparent, foreground: OmiColors.textPrimary),
      OmiButtonVariant.toolbar => (background: OmiColors.surface1, foreground: OmiColors.textPrimary),
    };
  }

  @override
  Widget build(BuildContext context) {
    final compact = widget.size == OmiButtonSize.compact;
    final enabled = widget.onPressed != null;
    final colors = _colors(enabled);
    final visualHeight = widget.height ?? (compact ? 36.0 : 48.0);
    final baseStyle = compact ? OmiType.subhead : OmiType.callout;
    final textStyle = (widget.labelStyle ?? baseStyle.copyWith(fontWeight: FontWeight.w600)).copyWith(
      color: colors.foreground,
    );

    Widget label = Text(widget.label, style: textStyle, maxLines: 1, overflow: TextOverflow.ellipsis);
    if (widget.leading != null || widget.icon != null) {
      final iconSize = compact ? 16.0 : 18.0;
      label = Row(
        mainAxisSize: MainAxisSize.min,
        children: [
          IconTheme(
            data: IconThemeData(size: iconSize, color: colors.foreground),
            child: widget.leading ?? Icon(widget.icon),
          ),
          const SizedBox(width: OmiSpacing.xs),
          Flexible(child: label),
        ],
      );
    }

    final content = Stack(
      alignment: Alignment.center,
      children: [
        // Keep the label laid out (and announced) while the spinner shows, so the button keeps
        // its width and a screen reader still hears what it does.
        Opacity(opacity: _loading ? 0 : 1, alwaysIncludeSemantics: true, child: label),
        if (_loading) OmiSpinner(size: OmiSpinnerSize.small, color: colors.foreground),
      ],
    );

    // A legacy fixed width owns its own sizing; keep the label from being squeezed by padding.
    final horizontalPadding = widget.width != null ? OmiSpacing.xs : (compact ? OmiSpacing.md : OmiSpacing.xl);
    Widget button = TextButton(
      onPressed: !enabled ? null : (_loading ? () {} : _handlePressed),
      style: ButtonStyle(
        backgroundColor: WidgetStatePropertyAll(colors.background),
        foregroundColor: WidgetStatePropertyAll(colors.foreground),
        overlayColor: WidgetStatePropertyAll(colors.foreground.withValues(alpha: 0.12)),
        elevation: const WidgetStatePropertyAll(0),
        padding: WidgetStatePropertyAll(EdgeInsets.symmetric(horizontal: horizontalPadding)),
        minimumSize: WidgetStatePropertyAll(Size(widget.width ?? visualHeight, visualHeight)),
        fixedSize: widget.width != null ? WidgetStatePropertyAll(Size(widget.width!, visualHeight)) : null,
        shape: const WidgetStatePropertyAll(RoundedRectangleBorder(borderRadius: OmiRadius.mdAll)),
        // A visual under 44pt gets padded out to a 48pt target; a 48pt button needs no padding.
        tapTargetSize: visualHeight < 44 ? MaterialTapTargetSize.padded : MaterialTapTargetSize.shrinkWrap,
        textStyle: WidgetStatePropertyAll(textStyle),
      ),
      child: content,
    );

    if (widget.expand) {
      button = SizedBox(width: double.infinity, child: button);
    }
    return button;
  }
}
