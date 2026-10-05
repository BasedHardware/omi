import 'package:flutter/material.dart';

import 'package:omi/ui/ui.dart';

/// Retry at the right end of a conversation list row, level with what it retries: "Try again" on
/// a processing row that is taking too long, "Retry" on a failed summary. While the retry runs, a
/// spinner takes the label's place at the label's width, so nothing in the row moves.
class ListRowRetryButton extends StatelessWidget {
  const ListRowRetryButton({super.key, required this.label, required this.busy, required this.onPressed});

  final String label;
  final bool busy;
  final VoidCallback onPressed;

  @override
  Widget build(BuildContext context) {
    return GestureDetector(
      onTap: () {}, // absorb so the row's open-on-tap does not fire
      child: TextButton(
        onPressed: busy ? null : onPressed,
        style: TextButton.styleFrom(
          foregroundColor: OmiColors.textPrimary,
          padding: const EdgeInsets.symmetric(horizontal: 12, vertical: 8),
          minimumSize: const Size(44, 44),
          tapTargetSize: MaterialTapTargetSize.shrinkWrap,
        ),
        child: Stack(
          alignment: Alignment.center,
          children: [
            Opacity(opacity: busy ? 0 : 1, child: Text(label)),
            if (busy) const OmiSpinner(size: OmiSpinnerSize.small),
          ],
        ),
      ),
    );
  }
}
