import 'package:flutter/material.dart';

import 'package:omi/pages/memories/widgets/memory_graph_page.dart';
import 'package:omi/utils/responsive/responsive_helper.dart';

/// The Brain tab.
///
/// One surface, top to bottom, and it is the *host's* surface: this page paints
/// no background of its own, so it inherits the black the enclosing Scaffold
/// already uses for every other tab. An earlier version stacked three
/// near-blacks in a single column (page #0F0F0F, card #1A1A1A, button #252525),
/// which reads as banding rather than as depth.
///
/// The graph itself is unchanged — it just gets the whole page to draw on.
class BrainPage extends StatelessWidget {
  const BrainPage({super.key});

  /// The bottom nav bar (height 100) floats over the page rather than taking
  /// layout space, so the graph reserves its height by hand — otherwise nodes
  /// settle underneath the bar where they can't be read or tapped.
  static const double _navBarClearance = 100;

  @override
  Widget build(BuildContext context) {
    return const SafeArea(
      bottom: false,
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          Padding(
            padding: EdgeInsets.fromLTRB(20, 12, 20, 12),
            child: Text(
              'Mind Map',
              style: TextStyle(color: ResponsiveHelper.textPrimary, fontSize: 22, fontWeight: FontWeight.w600),
            ),
          ),
          Expanded(
            // ClipRect, not ClipRRect: node glows must not paint up into the
            // header, but the clip adds no surface of its own.
            child: ClipRect(
              child: Padding(
                padding: EdgeInsets.only(bottom: _navBarClearance),
                child: MemoryGraphPage(embedded: true, trackOpenEvent: false, showShareButton: false),
              ),
            ),
          ),
        ],
      ),
    );
  }
}
