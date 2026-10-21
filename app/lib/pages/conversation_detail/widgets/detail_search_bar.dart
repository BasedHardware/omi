import 'package:flutter/material.dart';

import 'package:omi/ui/ui.dart';
import 'package:omi/utils/l10n_extensions.dart';

/// The in-conversation search bar: the shared search field, a "2/7" result position with
/// previous/next controls once there is a query, and Cancel to leave search.
class DetailSearchBar extends StatelessWidget {
  const DetailSearchBar({
    super.key,
    required this.controller,
    required this.focusNode,
    required this.query,
    required this.currentIndex,
    required this.totalResults,
    required this.onChanged,
    required this.onPrevious,
    required this.onNext,
    required this.onCancel,
  });

  final TextEditingController controller;
  final FocusNode focusNode;
  final String query;

  /// 1-based position of the highlighted match; 0 when nothing matches.
  final int currentIndex;
  final int totalResults;
  final ValueChanged<String> onChanged;
  final VoidCallback onPrevious;
  final VoidCallback onNext;
  final VoidCallback onCancel;

  @override
  Widget build(BuildContext context) {
    final hasResults = totalResults > 0;
    return Container(
      color: OmiColors.surface0,
      padding: const EdgeInsets.fromLTRB(OmiSpacing.md, OmiSpacing.xs, OmiSpacing.xs, OmiSpacing.xs),
      child: Row(
        children: [
          Expanded(
            child: OmiSearchField(
              placeholder: context.l10n.searchTranscriptOrSummary,
              controller: controller,
              focusNode: focusNode,
              onChanged: onChanged,
            ),
          ),
          if (query.isNotEmpty) ...[
            const SizedBox(width: OmiSpacing.xs),
            Text(
              '$currentIndex/$totalResults',
              style: OmiType.footnote.copyWith(color: OmiColors.textSecondary),
            ),
            OmiIconButton(
              icon: const Icon(Icons.keyboard_arrow_up),
              label: context.l10n.previousResult,
              color: OmiColors.textSecondary,
              onPressed: hasResults ? onPrevious : null,
            ),
            OmiIconButton(
              icon: const Icon(Icons.keyboard_arrow_down),
              label: context.l10n.nextResult,
              color: OmiColors.textSecondary,
              onPressed: hasResults ? onNext : null,
            ),
          ],
          OmiButton.tertiary(label: context.l10n.cancel, size: OmiButtonSize.compact, onPressed: onCancel),
        ],
      ),
    );
  }
}
