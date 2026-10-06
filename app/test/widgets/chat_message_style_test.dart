import 'package:flutter/material.dart';
import 'package:flutter_markdown/flutter_markdown.dart';
import 'package:font_awesome_flutter/font_awesome_flutter.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:provider/provider.dart';

import 'package:omi/backend/schema/message.dart';
import 'package:omi/l10n/app_localizations.dart';
import 'package:omi/pages/chat/widgets/ai_message.dart';
import 'package:omi/pages/chat/widgets/chat_bubbles.dart';
import 'package:omi/pages/chat/widgets/chat_followup_chip.dart';
import 'package:omi/pages/chat/widgets/markdown_message_widget.dart';
import 'package:omi/pages/chat/widgets/user_message.dart';
import 'package:omi/providers/connectivity_provider.dart';
import 'package:omi/providers/conversation_provider.dart';
import 'package:omi/ui/ui.dart';

void main() {
  Future<void> pump(WidgetTester tester, Widget child) => tester.pumpWidget(
        MaterialApp(
          theme: buildOmiTheme(),
          localizationsDelegates: AppLocalizations.localizationsDelegates,
          supportedLocales: AppLocalizations.supportedLocales,
          home: Scaffold(body: child),
        ),
      );

  ServerMessage aiMessage(String text, {List<MessageConversation> memories = const []}) => ServerMessage(
        'a1',
        DateTime.utc(2026),
        text,
        MessageSender.ai,
        MessageType.text,
        null,
        false,
        [],
        [],
        memories,
      );

  Widget answer(ServerMessage message) => AIMessage(
        message: message,
        sendMessage: (_) {},
        displayOptions: false,
        updateConversation: (_) {},
        setMessageNps: (int value, {String? reason}) {},
      );

  testWidgets('the question sits in a solid accent pill with the Messages tail', (tester) async {
    final message = ServerMessage(
      'q1',
      DateTime.utc(2026),
      'Did Dan send the model link?',
      MessageSender.human,
      MessageType.text,
      null,
      false,
      [],
      [],
      [],
    );
    await pump(tester, HumanMessage(message: message));

    final box = tester.widget<Container>(find.byKey(const Key('chat_user_message')));
    final decoration = box.decoration! as BoxDecoration;
    expect(decoration.color, OmiColors.accent, reason: 'the accent: black in light, white in dark');
    expect(decoration.border, isNull, reason: 'a fill, not an outline');
    expect(decoration.borderRadius, OmiRadius.lgAll);
    expect(find.byKey(const Key('chat_user_message_tail')), findsOneWidget);
    final words = tester.widget<SelectableText>(find.byType(SelectableText));
    expect(words.style!.color, OmiColors.onAccent, reason: 'the words read on the fill');
    expect(words.style!.fontSize, OmiType.body.fontSize);
    expect(find.text('Did Dan send the model link?'), findsOneWidget);
  });

  testWidgets("Omi's answer is text on the page, with no box around it", (tester) async {
    await pump(tester, answer(aiMessage('Not sure. Nothing about that today.')));

    final boxed = find.ancestor(
      of: find.byType(MarkdownBody),
      matching: find.byWidgetPredicate((widget) => widget is Container && widget.decoration != null),
    );
    expect(boxed, findsNothing, reason: 'no card, no fill, no outline behind the words');
    expect(find.text('Not sure. Nothing about that today.'), findsOneWidget);
    expect(find.byType(MessageActionBar), findsOneWidget);
  });

  testWidgets("Omi's answer is larger than the question's callout, in a regular weight, and no heading is smaller",
      (tester) async {
    await pump(
        tester, Builder(builder: (context) => getMarkdownWidget(context, 'Not sure. Nothing about that today.')));

    final sheet = tester.widget<MarkdownBody>(find.byType(MarkdownBody)).styleSheet!;
    final words = sheet.p!;
    expect(words.fontSize, greaterThan(OmiType.callout.fontSize!));
    expect(words.fontWeight, FontWeight.w400);
    expect(sheet.listBullet!.fontSize, words.fontSize, reason: 'list items read at the same size as the words');
    for (final heading in [sheet.h1, sheet.h2, sheet.h3, sheet.h4, sheet.h5, sheet.h6]) {
      expect(heading!.fontSize, greaterThanOrEqualTo(words.fontSize!));
    }
    expect(find.text('Not sure. Nothing about that today.'), findsOneWidget);
  });

  testWidgets('a "[1]" pointing at a source is small and quiet, inside its sentence', (tester) async {
    await pump(
      tester,
      Builder(
          builder: (context) => getMarkdownWidget(context, 'Not about the V2 yet. [1] See [the doc](https://omi.me).')),
    );

    final paragraph = tester.widget<RichText>(find.byWidgetPredicate(
      (widget) => widget is RichText && widget.text.toPlainText().contains('Not about the V2 yet.'),
    ));
    expect(paragraph.text.toPlainText(), contains('[1]'),
        reason: 'the marker stays in the sentence, not on its own line');
    TextStyle? markerStyle;
    paragraph.text.visitChildren((span) {
      if (span is TextSpan && span.text == '[1]') markerStyle = span.style;
      return markerStyle == null;
    });
    expect(markerStyle?.fontSize, OmiType.footnote.fontSize);
    expect(markerStyle?.color, OmiColors.textTertiary);
    expect(paragraph.text.toPlainText(), contains('the doc'), reason: 'a real link is untouched');
  });

  testWidgets('the sources are a plain numbered list under the answer: no emoji, no card, hairlines between',
      (tester) async {
    final when = DateTime.parse('2026-10-02T19:12:00Z');
    final message = aiMessage('Not about the V2 yet. [1]', memories: [
      MessageConversation('c1', when, MessageConversationStructured('Testing Omi Offline Speech', '🎙️')),
      MessageConversation('c2', when, MessageConversationStructured('App UX and Battery Concerns', '📱')),
    ]);
    final conversations = ConversationProvider(isSignedIn: () => false);
    addTearDown(conversations.dispose);
    await tester.pumpWidget(
      MultiProvider(
        providers: [
          ChangeNotifierProvider.value(value: conversations),
          ChangeNotifierProvider(create: (_) => ConnectivityProvider()),
        ],
        child: MaterialApp(
          theme: buildOmiTheme(),
          localizationsDelegates: AppLocalizations.localizationsDelegates,
          supportedLocales: AppLocalizations.supportedLocales,
          home: Scaffold(body: SingleChildScrollView(child: answer(message))),
        ),
      ),
    );

    final list = find.byKey(const ValueKey('chat-citation-list'));
    expect(list, findsOneWidget);
    expect(tester.widget(list), isA<Padding>(), reason: 'a list on the page, not a card');
    expect(find.byKey(const ValueKey('chat-citation-c1')), findsOneWidget);
    expect(find.text('1'), findsOneWidget);
    expect(find.text('2'), findsOneWidget);
    expect(find.text('Testing Omi Offline Speech'), findsOneWidget);
    expect(find.textContaining('🎙️'), findsNothing, reason: 'no emoji tiles');
    expect(find.textContaining('📱'), findsNothing);
    final separator = tester.widget<Divider>(find.byType(Divider));
    expect(separator.color, ChatInk.sep, reason: 'one hairline between the two rows');
    final number = tester.widget<Text>(find.byKey(const Key('chat_citation_number')).first);
    expect(number.style!.color, OmiColors.textTertiary);
  });

  testWidgets('the follow-up is a filled pill with the reply arrow, and a failed reply a filled box', (tester) async {
    await pump(tester, ChatFollowUpChip(question: 'Which one is due first?', onSend: (_) {}));

    expect(find.byIcon(Icons.subdirectory_arrow_right), findsOneWidget);
    final button = tester.widget<OutlinedButton>(find.byKey(const Key('chat_followup_chip')));
    expect(button.style!.backgroundColor!.resolve({}), ChatInk.fill, reason: 'the ink at an opacity');
    expect(button.style!.side!.resolve({})!.style, BorderStyle.none, reason: 'no outline');
    expect(find.text('Which one is due first?'), findsOneWidget);

    await pump(tester, ChatReplyError(onRetry: () {}));
    final box = tester.widget<Container>(
      find.ancestor(of: find.text('Try Again'), matching: find.byType(Container)).first,
    );
    final decoration = box.decoration! as BoxDecoration;
    expect(decoration.color, ChatInk.fill);
    expect(decoration.border, isNull);
  });

  testWidgets('Copy, Helpful, Not Helpful and Share are small quiet glyphs on 44 pt targets', (tester) async {
    await pump(tester, const MessageActionBar(messageText: 'An answer'));

    final glyphs = tester.widgetList<FaIcon>(find.byType(FaIcon)).toList();
    expect(glyphs, hasLength(4));
    for (final glyph in glyphs) {
      expect(glyph.size, 15);
      expect(glyph.color, OmiColors.textTertiary);
    }
    for (final label in ['Copy Message', 'Helpful', 'Not Helpful', 'Share']) {
      expect(tester.getSize(find.bySemanticsLabel(label)), const Size(44, 44));
    }
  });
}
