// The end of a list whose next page failed to load; owns its one quiet line and its retry tap
// (ux-contract §17, X6). Not a row and not a button: tertiary text, tappable, a spinner while it retries.

import 'package:flutter/material.dart';

import 'package:omi/ui/components/omi_spinner.dart';
import 'package:omi/ui/omi_tokens.dart';
import 'package:omi/utils/l10n_extensions.dart';

/// "Couldn't load older ones. Tap to retry." at the end of a list. A tap runs [onRetry] and shows a
/// small spinner in the line's place until it settles; the list replaces the line once a page lands.
class OmiLoadMoreFailed extends StatefulWidget {
  const OmiLoadMoreFailed({super.key, required this.onRetry});

  final Future<void> Function() onRetry;

  @override
  State<OmiLoadMoreFailed> createState() => _OmiLoadMoreFailedState();
}

class _OmiLoadMoreFailedState extends State<OmiLoadMoreFailed> {
  bool _retrying = false;

  Future<void> _retry() async {
    if (_retrying) return;
    setState(() => _retrying = true);
    try {
      await widget.onRetry();
    } finally {
      if (mounted) setState(() => _retrying = false);
    }
  }

  @override
  Widget build(BuildContext context) {
    final label = context.l10n.loadOlderFailed;
    return Semantics(
      button: true,
      liveRegion: true,
      label: label,
      excludeSemantics: true,
      child: GestureDetector(
        behavior: HitTestBehavior.opaque,
        onTap: _retry,
        child: ConstrainedBox(
          constraints: const BoxConstraints(minHeight: 44, minWidth: double.infinity),
          child: Padding(
            padding: const EdgeInsets.symmetric(horizontal: OmiSpacing.md, vertical: OmiSpacing.sm),
            child: Center(
              child: AnimatedSwitcher(
                duration: OmiMotion.of(context).quick,
                child: _retrying
                    ? const OmiSpinner(key: ValueKey('load_more_retrying'), size: OmiSpinnerSize.small)
                    : Text(
                        label,
                        key: const ValueKey('load_more_failed_text'),
                        textAlign: TextAlign.center,
                        style: OmiType.footnote.copyWith(color: OmiColors.textTertiary),
                      ),
              ),
            ),
          ),
        ),
      ),
    );
  }
}
