// Copyright 2024 BasedHardware Ltd
// SPDX-License-Identifier: Apache-2.0

import 'package:flutter/material.dart';
import 'package:omi/app/lib/pages/memories/widgets/memory_graph_page.dart';
import 'package:omi/app/lib/widgets/app_bar/app_bar.dart';
import 'package:omi/app/lib/constants/app_colors.dart';

/// The "Here is what I know about you" onboarding step.
///
/// Renders a small knowledge graph with a reduced zoom (0.72) so the entire
/// graph fits within the panel. The actual framing is computed by
/// [MemoryGraphPage._frameToFit] after layout.
class KnowledgeGraphStep extends StatelessWidget {
  final List<dynamic> memories;
  final VoidCallback onNext;

  const KnowledgeGraphStep({
    super.key,
    required this.memories,
    required this.onNext,
  });

  @override
  Widget build(BuildContext context) {
    return Scaffold(
      appBar: AppBar(
        title: const Text('Here is what I know about you'),
        backgroundColor: AppColors.background,
        foregroundColor: AppColors.text,
      ),
      body: MemoryGraphPage(
        nodes: memories,
        edges: const [],
        nodeColor: AppColors.primary,
        edgeColor: AppColors.muted,
        // Reduced initial zoom for onboarding so the graph looks approachable.
        // The actual zoom is adjusted after layout via _frameToFit.
        showEdges: false,
      ),
      floatingActionButton: FloatingActionButton.extended(
        onPressed: onNext,
        backgroundColor: AppColors.primary,
        foregroundColor: Colors.white,
        label: const Text('Continue'),
        icon: const Icon(Icons.arrow_forward),
      ),
    );
  }
}
