import 'package:flutter/material.dart';

import 'package:omi/pages/memories/widgets/memory_graph_page.dart';
import 'package:omi/utils/responsive/responsive_helper.dart';

/// The Brain tab.
///
/// The knowledge graph is rendered as a *contained section* rather than a
/// full-bleed page: it sits on its own darker surface, inset from the page
/// edges and clipped to a rounded rectangle, so it reads as one object on the
/// page instead of as the page itself. Full-bleed made nodes bleed off every
/// edge with no boundary to tell the user where the graph ended.
class BrainPage extends StatelessWidget {
  const BrainPage({super.key});

  /// The graph sits on a raised grey surface against the page's deep black,
  /// so the section reads as a card laid on the page.
  static const Color _canvasColor = ResponsiveHelper.backgroundSecondary;

  /// The bottom nav bar (height 100) floats over the page rather than taking
  /// layout space, so the card must clear it by hand or its bottom corners are
  /// hidden behind the bar.
  static const double _navBarClearance = 100 + 16;

  @override
  Widget build(BuildContext context) {
    return ColoredBox(
      // Matches the colour the nav bar's gradient resolves to, so the page and
      // the bar read as one continuous surface behind the card.
      color: ResponsiveHelper.backgroundPrimary,
      child: SafeArea(
        bottom: false,
        child: Column(
          crossAxisAlignment: CrossAxisAlignment.start,
          children: [
            const _SectionHeader(),
            Expanded(
              child: Padding(
                padding: const EdgeInsets.fromLTRB(16, 0, 16, _navBarClearance),
                child: DecoratedBox(
                  decoration: BoxDecoration(
                    color: _canvasColor,
                    borderRadius: BorderRadius.circular(28),
                    border: Border.all(color: Colors.white.withValues(alpha: 0.06)),
                  ),
                  child: ClipRRect(
                    // Inset by the border width so node glows never paint over
                    // the stroke that defines the section edge.
                    borderRadius: BorderRadius.circular(27),
                    child: const MemoryGraphPage(
                      embedded: true,
                      trackOpenEvent: false,
                      showShareButton: false,
                    ),
                  ),
                ),
              ),
            ),
          ],
        ),
      ),
    );
  }
}

class _SectionHeader extends StatelessWidget {
  const _SectionHeader();

  @override
  Widget build(BuildContext context) {
    return Padding(
      padding: const EdgeInsets.fromLTRB(20, 12, 12, 12),
      child: Row(
        children: [
          const Expanded(
            child: Text(
              'Mind Map',
              style: TextStyle(
                color: ResponsiveHelper.textPrimary,
                fontSize: 22,
                fontWeight: FontWeight.w600,
              ),
            ),
          ),
          TextButton(
            onPressed: () {
              Navigator.of(context, rootNavigator: true).push(
                MaterialPageRoute(builder: (_) => const MemoryGraphPage()),
              );
            },
            style: TextButton.styleFrom(
              backgroundColor: ResponsiveHelper.backgroundTertiary,
              foregroundColor: ResponsiveHelper.textSecondary,
              padding: const EdgeInsets.symmetric(horizontal: 16, vertical: 8),
              shape: RoundedRectangleBorder(borderRadius: BorderRadius.circular(20)),
            ),
            child: const Text(
              'Expand',
              style: TextStyle(fontSize: 14, fontWeight: FontWeight.w500),
            ),
          ),
        ],
      ),
    );
  }
}
