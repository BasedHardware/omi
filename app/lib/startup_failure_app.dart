import 'dart:ui' as ui;

import 'package:flutter/foundation.dart';
import 'package:flutter/material.dart';

import 'package:url_launcher/url_launcher.dart';

import 'package:omi/l10n/app_localizations.dart';
import 'package:omi/l10n/app_localizations_en.dart';
import 'package:omi/ui/components/omi_spinner.dart';
import 'package:omi/ui/omi_tokens.dart';

/// A startup check rejected how this build is configured (environment profile, API endpoint).
/// Retrying cannot fix it, so the failure screen offers support instead of Try Again.
class StartupConfigurationError implements Exception {
  const StartupConfigurationError(this.cause);

  final Object cause;

  @override
  String toString() => '$cause';
}

const String kStartupSupportEmail = 'team@basedhardware.com';

/// Minimum touch target (the design system's 44pt, without importing its widgets).
const double _kTapTarget = 44;

/// Shown when `_init()` throws before the app's first frame.
///
/// The raw error sits behind a collapsed "Details" disclosure (open by default for a configuration
/// error, whose message points at it).
///
/// Deliberately self-contained: no providers, no services and no theme lookups. Everything it could
/// depend on is exactly what may have just failed to initialise, so it renders from Flutter, the
/// design tokens (plain constants), the stateless [OmiSpinner] and the generated strings, looked up
/// for the device locale without a localisation scope (English when the locale is not supported).
///
/// Without this the app sits on the launch storyboard indefinitely — `runApp()`
/// never runs, and `debugPrint` from the zone handler is invisible in profile
/// and release builds. A startup guard rejecting a misconfigured
/// `OMI_API_BASE_URL` is a precise, actionable error; presenting it as a blank
/// splash screen is what made it expensive to diagnose.
///
/// The wording follows the error class: a [StartupConfigurationError] says the build is at fault and
/// offers Contact Support; anything else offers Try Again ([onRetry], which re-runs start-up) and
/// Contact Support.
class StartupFailureApp extends StatelessWidget {
  const StartupFailureApp({super.key, required this.error, this.stack, this.onRetry});

  final Object error;
  final StackTrace? stack;

  /// Re-runs start-up. Null hides Try Again.
  final Future<void> Function()? onRetry;

  bool get _isConfiguration => error is StartupConfigurationError;

  static Uri _supportUri(AppLocalizations l10n) => Uri(
        scheme: 'mailto',
        path: kStartupSupportEmail,
        query: 'subject=${Uri.encodeComponent(l10n.startupFailedTitle)}',
      );

  static AppLocalizations _strings() {
    try {
      return lookupAppLocalizations(ui.PlatformDispatcher.instance.locale);
    } catch (_) {
      return AppLocalizationsEn();
    }
  }

  @override
  Widget build(BuildContext context) {
    final l10n = _strings();
    final retry = _isConfiguration ? null : onRetry;
    final details = (kDebugMode || kProfileMode) && stack != null ? '$error\n\n$stack' : '$error';
    return MaterialApp(
      debugShowCheckedModeBanner: false,
      home: Scaffold(
        backgroundColor: OmiColors.surface0,
        body: SafeArea(
          // Centred like the app's other error states: glyph, title, message, actions, and the raw
          // error behind a Details disclosure that support can ask for.
          child: LayoutBuilder(
            builder: (context, constraints) => SingleChildScrollView(
              padding: const EdgeInsets.all(OmiSpacing.xl),
              child: ConstrainedBox(
                constraints: BoxConstraints(minHeight: constraints.maxHeight - OmiSpacing.xl * 2),
                child: Center(
                  child: ConstrainedBox(
                    constraints: const BoxConstraints(maxWidth: 400),
                    child: Column(
                      mainAxisSize: MainAxisSize.min,
                      crossAxisAlignment: CrossAxisAlignment.stretch,
                      children: [
                        ExcludeSemantics(child: Icon(Icons.error_outline, size: 40, color: OmiColors.textTertiary)),
                        const SizedBox(height: OmiSpacing.md),
                        Semantics(
                          header: true,
                          child: Text(l10n.startupFailedTitle, style: OmiType.title2, textAlign: TextAlign.center),
                        ),
                        const SizedBox(height: OmiSpacing.xs),
                        Text(
                          _isConfiguration ? l10n.startupFailedConfigMessage : l10n.startupFailedMessage,
                          textAlign: TextAlign.center,
                          style: OmiType.subhead.copyWith(color: OmiColors.textSecondary, height: 1.4),
                        ),
                        const SizedBox(height: OmiSpacing.xl),
                        if (retry != null) ...[
                          _RetryButton(label: l10n.tryAgain, onRetry: retry),
                          const SizedBox(height: OmiSpacing.xs),
                        ],
                        TextButton(
                          key: const Key('startup_failure_contact_support'),
                          style: TextButton.styleFrom(
                            foregroundColor: OmiColors.textPrimary,
                            minimumSize: const Size.fromHeight(_kTapTarget),
                          ),
                          onPressed: () => launchUrl(_supportUri(l10n)),
                          child: Text(l10n.contactSupportAction, style: OmiType.headline),
                        ),
                        const SizedBox(height: OmiSpacing.md),
                        // A configuration message points at "the details below", so it opens them.
                        _ErrorDetails(label: l10n.startupFailedDetails, text: details, initiallyOpen: _isConfiguration),
                      ],
                    ),
                  ),
                ),
              ),
            ),
          ),
        ),
      ),
    );
  }
}

/// The raw error, collapsed under "Details" until someone (usually support) asks for it. Selectable
/// so it can be copied off a device with no debugger attached, which is the situation this screen
/// exists for.
class _ErrorDetails extends StatefulWidget {
  const _ErrorDetails({required this.label, required this.text, required this.initiallyOpen});

  final String label;
  final String text;
  final bool initiallyOpen;

  @override
  State<_ErrorDetails> createState() => _ErrorDetailsState();
}

class _ErrorDetailsState extends State<_ErrorDetails> {
  late bool _open = widget.initiallyOpen;

  @override
  Widget build(BuildContext context) {
    return Column(
      crossAxisAlignment: CrossAxisAlignment.stretch,
      children: [
        Center(
          child: Semantics(
            expanded: _open,
            child: TextButton(
              key: const Key('startup_failure_details'),
              style: TextButton.styleFrom(
                foregroundColor: OmiColors.textSecondary,
                minimumSize: const Size(_kTapTarget, _kTapTarget),
              ),
              onPressed: () => setState(() => _open = !_open),
              child: Row(
                mainAxisSize: MainAxisSize.min,
                children: [
                  Text(widget.label, style: OmiType.footnote.copyWith(color: OmiColors.textSecondary)),
                  const SizedBox(width: OmiSpacing.xxs),
                  ExcludeSemantics(
                    child: Icon(
                      _open ? Icons.expand_less : Icons.expand_more,
                      size: 18,
                      color: OmiColors.textSecondary,
                    ),
                  ),
                ],
              ),
            ),
          ),
        ),
        if (_open)
          Container(
            margin: const EdgeInsets.only(top: OmiSpacing.xs),
            padding: const EdgeInsets.all(OmiSpacing.sm),
            decoration: BoxDecoration(color: OmiColors.surface1, borderRadius: OmiRadius.mdAll),
            child: SelectableText(
              widget.text,
              style: OmiType.footnote.copyWith(color: OmiColors.textTertiary, height: 1.4),
            ),
          ),
      ],
    );
  }
}

/// Try Again with a busy state, so a second tap cannot start two start-ups.
class _RetryButton extends StatefulWidget {
  const _RetryButton({required this.label, required this.onRetry});

  final String label;
  final Future<void> Function() onRetry;

  @override
  State<_RetryButton> createState() => _RetryButtonState();
}

class _RetryButtonState extends State<_RetryButton> {
  bool _busy = false;

  Future<void> _retry() async {
    setState(() => _busy = true);
    try {
      await widget.onRetry();
    } finally {
      if (mounted) setState(() => _busy = false);
    }
  }

  @override
  Widget build(BuildContext context) {
    return FilledButton(
      key: const Key('startup_failure_try_again'),
      style: FilledButton.styleFrom(
        backgroundColor: OmiColors.accent,
        foregroundColor: OmiColors.onAccent,
        minimumSize: const Size.fromHeight(_kTapTarget + 6),
        shape: const RoundedRectangleBorder(borderRadius: OmiRadius.pillAll),
      ),
      onPressed: _busy ? null : _retry,
      child: _busy
          ? OmiSpinner(size: OmiSpinnerSize.small, color: OmiColors.onAccent, label: widget.label)
          : Text(widget.label, style: OmiType.headline.copyWith(color: OmiColors.onAccent)),
    );
  }
}
