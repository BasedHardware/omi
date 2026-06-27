import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:provider/provider.dart';

import 'package:omi/pages/chat/reply_draft_page.dart';
import 'package:omi/providers/reply_draft_provider.dart';

void main() {
  testWidgets('reply draft page renders the review-first composer', (tester) async {
    tester.view.physicalSize = const Size(1080, 2200);
    tester.view.devicePixelRatio = 1;
    addTearDown(tester.view.resetPhysicalSize);
    addTearDown(tester.view.resetDevicePixelRatio);

    await tester.pumpWidget(
      ChangeNotifierProvider(
        create: (_) => ReplyDraftProvider(),
        child: const MaterialApp(home: ReplyDraftPage()),
      ),
    );

    expect(find.text('Draft reply'), findsWidgets);
    expect(find.text('Message to answer'), findsOneWidget);

    await tester.tap(find.byIcon(Icons.auto_fix_high_rounded));
    await tester.pump();

    expect(find.text('Paste the message you want to answer first.'), findsOneWidget);
  });
}
