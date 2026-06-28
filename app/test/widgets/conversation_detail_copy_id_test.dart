import 'package:flutter/material.dart';
import 'package:flutter/services.dart';
import 'package:flutter_localizations/flutter_localizations.dart';
import 'package:flutter_test/flutter_test.dart';

import 'package:omi/l10n/app_localizations.dart';

/// Wraps [child] in a MaterialApp configured with all l10n delegates so
/// `AppLocalizations.of(context)!.copyConversationId` etc. resolve.
/// `locale` defaults to English; pass another supported locale (e.g. `ja`)
/// to test the localized snackbar wording.
Widget buildTestApp(Widget child, {Locale locale = const Locale('en')}) {
  return MaterialApp(
    locale: locale,
    localizationsDelegates: const [
      AppLocalizations.delegate,
      GlobalMaterialLocalizations.delegate,
      GlobalWidgetsLocalizations.delegate,
      GlobalCupertinoLocalizations.delegate,
    ],
    supportedLocales: AppLocalizations.supportedLocales,
    home: child,
  );
}

/// Reproduces the inline body of the `'copy_conversation_id'` branch in
/// `_handleMenuSelection` (`app/lib/pages/conversation_detail/page.dart`).
/// Keeping this harness in lockstep with the real menu item lets the
/// behavior — Clipboard write + localized snackbar — be tested without
/// pumping the full `ConversationDetailPage` widget tree (which would
/// require many providers / network mocks).
///
/// **Sync requirement:** because this harness re-implements the production
/// branch instead of importing it, any future change to that switch case
/// (e.g. swapping `Clipboard.setData` semantics, replacing the snackbar with
/// a toast, or routing through `_copyContent`) must be mirrored here, or
/// these tests will keep passing against stale behavior.
class CopyConversationIdHarness extends StatelessWidget {
  const CopyConversationIdHarness({super.key, required this.conversationId});

  final String conversationId;

  @override
  Widget build(BuildContext context) {
    return Scaffold(
      body: Center(
        child: Builder(
          builder: (innerContext) {
            return ElevatedButton(
              onPressed: () {
                Clipboard.setData(ClipboardData(text: conversationId));
                ScaffoldMessenger.of(innerContext).showSnackBar(
                  SnackBar(
                    content: Text(AppLocalizations.of(innerContext)!.conversationIdCopied),
                  ),
                );
                HapticFeedback.lightImpact();
              },
              child: const Text('Tap to copy'),
            );
          },
        ),
      ),
    );
  }
}

void main() {
  group('AppLocalizations strings (en)', () {
    testWidgets('copyConversationId exposes the menu label', (tester) async {
      late AppLocalizations l10n;
      await tester.pumpWidget(
        buildTestApp(
          Builder(
            builder: (context) {
              l10n = AppLocalizations.of(context)!;
              return const SizedBox.shrink();
            },
          ),
        ),
      );
      expect(l10n.copyConversationId, 'Copy Conversation ID');
    });

    testWidgets('conversationIdCopied exposes the snackbar message', (tester) async {
      late AppLocalizations l10n;
      await tester.pumpWidget(
        buildTestApp(
          Builder(
            builder: (context) {
              l10n = AppLocalizations.of(context)!;
              return const SizedBox.shrink();
            },
          ),
        ),
      );
      expect(l10n.conversationIdCopied, 'Conversation ID copied to clipboard');
    });
  });

  group('Copy Conversation ID action', () {
    testWidgets('writes the conversation id to the system clipboard', (tester) async {
      String? copied;
      tester.binding.defaultBinaryMessenger.setMockMethodCallHandler(
        SystemChannels.platform,
        (MethodCall call) async {
          if (call.method == 'Clipboard.setData') {
            copied = (call.arguments as Map)['text'] as String?;
          }
          return null;
        },
      );
      // Use addTearDown so the mock handler is reset even if the test fails
      // partway through, preventing leakage into the next testWidgets case.
      addTearDown(() {
        tester.binding.defaultBinaryMessenger.setMockMethodCallHandler(SystemChannels.platform, null);
      });

      const conversationId = 'conv_2026demo_abcdef0123456789';
      await tester.pumpWidget(
        buildTestApp(const CopyConversationIdHarness(conversationId: conversationId)),
      );

      await tester.tap(find.text('Tap to copy'));
      await tester.pump();

      expect(copied, conversationId);
      expect(find.text('Conversation ID copied to clipboard'), findsOneWidget);
    });

    testWidgets('snackbar wording is localized for non-English locales', (tester) async {
      tester.binding.defaultBinaryMessenger.setMockMethodCallHandler(
        SystemChannels.platform,
        (MethodCall call) async => null,
      );
      addTearDown(() {
        tester.binding.defaultBinaryMessenger.setMockMethodCallHandler(SystemChannels.platform, null);
      });

      await tester.pumpWidget(
        buildTestApp(
          const CopyConversationIdHarness(conversationId: 'irrelevant'),
          locale: const Locale('ja'),
        ),
      );

      await tester.tap(find.text('Tap to copy'));
      await tester.pump();

      // Value comes from app/lib/l10n/app_ja.arb and proves the generated
      // AppLocalizations actually surfaces the new key in non-English ARBs.
      expect(find.text('会話IDをクリップボードにコピーしました'), findsOneWidget);
    });
  });
}
