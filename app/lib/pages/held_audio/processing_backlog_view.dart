import 'package:flutter/material.dart';

import 'package:omi/models/subscription.dart';
import 'package:omi/ui/ui.dart';
import 'package:omi/utils/l10n_extensions.dart';

/// Shared boundary for retired backlog cards on Home, live and Usage surfaces.
class ProcessingBacklogView extends StatelessWidget {
  const ProcessingBacklogView({
    super.key,
    required this.backlog,
    required this.surface,
    required this.onUpgrade,
    this.onProcess,
    this.phoneAction,
  });

  final ProcessingBacklog backlog;
  final String surface;
  final VoidCallback onUpgrade;
  final Future<bool> Function()? onProcess;
  final Widget? phoneAction;

  // Retained as the shared surface boundary so backlog snapshots never expose
  // manual processing or plan actions. Recording state remains owned by providers.
  @override
  Widget build(BuildContext context) => const SizedBox.shrink();
}

class ProcessingDeferredMarker extends StatelessWidget {
  const ProcessingDeferredMarker({super.key});

  @override
  Widget build(BuildContext context) => Text(
        context.l10n.processingDeferred,
        key: const Key('processing_deferred_marker'),
        style: OmiType.footnote.copyWith(color: OmiColors.textSecondary),
      );
}
