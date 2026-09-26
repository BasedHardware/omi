import 'package:flutter/material.dart';

import 'package:collection/collection.dart';
import 'package:provider/provider.dart';

import 'package:omi/pages/conversation_detail/conversation_detail_provider.dart';
import 'package:omi/pages/conversation_detail/widgets/summarized_apps_sheet.dart';
import 'package:omi/ui/ui.dart';
import 'package:omi/utils/l10n_extensions.dart';

/// "Summary style" (v2 Conversation): which app writes this summary ("Default" or the app's name),
/// opening the chooser. Replaces the summary pill of the old floating bar.
class SummaryStyleRow extends StatelessWidget {
  const SummaryStyleRow({super.key});

  @override
  Widget build(BuildContext context) {
    final l10n = context.l10n;
    return Consumer<ConversationDetailProvider>(
      builder: (context, provider, _) {
        final selection = provider.getSummarySelection();
        final app = selection.isApp ? provider.appsList.firstWhereOrNull((a) => a.id == selection.appId) : null;
        final value = selection.isApp ? (app?.name ?? l10n.unknownApp) : l10n.defaultLabel;
        return OmiSettingsGroup(
          children: [
            OmiSettingsRow(
              key: const Key('conversation_summary_style'),
              leading: const OmiGlyph(OmiGlyphs.doc),
              title: l10n.summaryStyle,
              subtitle: l10n.summaryStyleSubtitle,
              value: value,
              onTap: () {
                OmiHaptics.selection();
                showSummarizedAppsSheet(context);
              },
            ),
          ],
        );
      },
    );
  }
}
