import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';

import 'package:omi/l10n/app_localizations.dart';
import 'package:omi/pages/conversations/widgets/folder_tabs.dart';
import 'package:omi/widgets/header_circle_button.dart';

void main() {
  testWidgets('filter chips and the add-folder button are full-height touch targets', (tester) async {
    await tester.pumpWidget(
      MaterialApp(
        localizationsDelegates: AppLocalizations.localizationsDelegates,
        supportedLocales: AppLocalizations.supportedLocales,
        home: Scaffold(
          body: Column(
            children: [
              FolderTabs(
                folders: const [],
                selectedFolderId: null,
                onFolderSelected: (_) {},
                showStarredOnly: false,
                onStarredToggle: () {},
                showDailySummaries: false,
                onDailySummariesToggle: () {},
                hasDailySummaries: false,
              ),
            ],
          ),
        ),
      ),
    );

    // The strip keeps the 52pt it always occupied (36pt chips + 8pt margins)...
    expect(tester.getSize(find.byType(FolderTabs)).height, 52);

    // ...but a chip's target is now the HIG's 44pt, around a 36pt painted pill.
    final chipTarget = find.ancestor(of: find.text('Starred'), matching: find.byType(GestureDetector)).first;
    expect(tester.getSize(chipTarget).height, kMinTapTarget);
    final pill = find.ancestor(of: find.text('Starred'), matching: find.byType(AnimatedContainer)).first;
    final decorated = find.descendant(of: pill, matching: find.byType(DecoratedBox)).first;
    expect(tester.getSize(decorated).height, 36);

    expect(tester.getSize(find.byType(HeaderCircleButton)), const Size(kMinTapTarget, kMinTapTarget));
  });
}
