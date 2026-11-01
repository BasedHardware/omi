import 'package:flutter/material.dart';
import 'package:flutter/rendering.dart';
import 'package:flutter/services.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:provider/provider.dart';

import 'package:omi/l10n/app_localizations.dart';
import 'package:omi/pages/conversations/widgets/merge_action_bar.dart';
import 'package:omi/pages/onboarding/auth.dart';
import 'package:omi/providers/auth_provider.dart';
import 'package:omi/providers/conversation_provider.dart';
import 'package:omi/ui/ui.dart';

import '../helpers/sfpro_font_fixtures.dart';

class _Auth extends AuthenticationProvider {
  _Auth({this.local = false}) : super(initializeListeners: false);

  final bool local;
  int appleTaps = 0;
  int googleTaps = 0;
  int localTaps = 0;

  @override
  bool get isLocalDevProfile => local;

  @override
  Future<void> onAppleSignIn(Function() onSignIn) async {
    appleTaps++;
  }

  @override
  Future<void> onGoogleSignIn(Function() onSignIn) async {
    googleTaps++;
  }

  @override
  Future<void> onLocalDevSignIn(Function() onSignIn) async {
    localTaps++;
  }
}

class _Conversations extends ChangeNotifier implements ConversationProvider {
  @override
  bool isSelectionModeActive = false;
  @override
  Set<String> selectedConversationIds = {};
  @override
  bool get canMerge => selectedConversationIds.length >= 2;
  @override
  void exitSelectionMode() {
    isSelectionModeActive = false;
    notifyListeners();
  }

  @override
  dynamic noSuchMethod(Invocation invocation) => super.noSuchMethod(invocation);
}

Widget _host(Widget child, {double scale = 1, Brightness brightness = Brightness.light}) {
  final theme = buildOmiTheme(brightness: brightness);
  return MaterialApp(
    theme: theme.copyWith(
      platform: TargetPlatform.iOS,
      textTheme: theme.textTheme.apply(fontFamily: 'SF Pro Display'),
    ),
    localizationsDelegates: AppLocalizations.localizationsDelegates,
    supportedLocales: const [Locale('en')],
    home: Builder(
      builder: (context) => MediaQuery(
        data: MediaQuery.of(context).copyWith(
          textScaler: TextScaler.linear(scale),
          padding: const EdgeInsets.only(top: 59, bottom: 34),
          viewPadding: const EdgeInsets.only(top: 59, bottom: 34),
        ),
        child: Scaffold(body: child),
      ),
    ),
  );
}

void main() {
  setUpAll(() async {
    // Manrope is unbundled; use the iOS fallback face for the headline too.
    for (final family in ['SF Pro Display', 'Manrope']) {
      final font = FontLoader(family);
      for (final weight in ['REGULAR', 'MEDIUM', 'BOLD']) {
        font.addFont(sfProFont('SFPRODISPLAY$weight.OTF'));
      }
      await font.load();
    }
  });

  for (final brightness in Brightness.values) {
    for (final scale in [1.0, 2.0, 3.1]) {
      testWidgets('sign-in actions remain visible and work repeatedly at $scale in $brightness', (tester) async {
        tester.view.physicalSize = const Size(320, 568);
        tester.view.devicePixelRatio = 1;
        addTearDown(tester.view.reset);
        final auth = _Auth();
        await tester.pumpWidget(ChangeNotifierProvider<AuthenticationProvider>.value(
          value: auth,
          child: _host(AuthComponent(onSignIn: () {}), scale: scale, brightness: brightness),
        ));
        await tester.pumpAndSettle();
        const headline = 'Speak. Transcribe. Summarize.';
        final headlineParagraph = tester.renderObject<RenderParagraph>(
          find.descendant(of: find.text(headline), matching: find.byType(RichText)),
        );
        expect(
          headlineParagraph.getBoxesForSelection(
            const TextSelection(baseOffset: headline.length - 'Summarize.'.length, extentOffset: headline.length),
          ),
          hasLength(1),
          reason: 'The hero headline must not leave the last letter of a word on its own line.',
        );
        for (final key in ['auth_sign_in_apple', 'auth_sign_in_google']) {
          final action = find.byKey(Key(key));
          expect(action.hitTestable(), findsOneWidget);
          final bounds = tester.getRect(action);
          expect(bounds.top, greaterThanOrEqualTo(59));
          expect(bounds.bottom, lessThanOrEqualTo(568 - 34));
          expect(bounds.height, greaterThanOrEqualTo(kOmiMinTapTarget));
          final labelText = find.descendant(
            of: action,
            matching: find.text(tester.widget<OmiButton>(action).label),
          );
          final label = find.descendant(of: labelText, matching: find.byType(RichText));
          expect(tester.renderObject<RenderParagraph>(label).didExceedMaxLines, isFalse);
          for (var i = 0; i < 3; i++) {
            await tester.tap(action);
            await tester.pumpAndSettle();
          }
        }
        expect(auth.appleTaps, 3);
        expect(auth.googleTaps, 3);
        expect(tester.takeException(), isNull);
      });
    }
  }

  testWidgets('local sign-in stays reachable at the largest accessibility text size', (tester) async {
    tester.view.physicalSize = const Size(320, 568);
    tester.view.devicePixelRatio = 1;
    addTearDown(tester.view.reset);
    final auth = _Auth(local: true);
    await tester.pumpWidget(ChangeNotifierProvider<AuthenticationProvider>.value(
      value: auth,
      child: _host(AuthComponent(onSignIn: () {}), scale: 3.1),
    ));
    await tester.pumpAndSettle();
    final action = find.byKey(const Key('auth_sign_in_local_dev'));
    expect(action.hitTestable(), findsOneWidget);
    await tester.tap(action);
    await tester.pumpAndSettle();
    expect(auth.localTaps, 1);
    expect(tester.takeException(), isNull);
  });

  testWidgets('Home has no selection shadow before or after repeated selection and cancel', (tester) async {
    final conversations = _Conversations();
    addTearDown(conversations.dispose);
    await tester.pumpWidget(ChangeNotifierProvider<ConversationProvider>.value(
      value: conversations,
      child: _host(const Stack(children: [Positioned(bottom: 0, left: 0, right: 0, child: MergeActionBar())])),
    ));
    bool paintsShadow() => tester.widgetList<Container>(find.byType(Container)).any(
          (widget) =>
              widget.decoration is BoxDecoration &&
              ((widget.decoration! as BoxDecoration).boxShadow?.isNotEmpty ?? false),
        );
    expect(paintsShadow(), isFalse);
    for (var i = 0; i < 3; i++) {
      conversations.isSelectionModeActive = true;
      conversations.notifyListeners();
      await tester.pumpAndSettle();
      expect(paintsShadow(), isTrue);
      expect(find.byKey(const Key('selection_bar_merge')).hitTestable(), findsOneWidget);
      await tester.tap(find.text('Cancel'));
      await tester.pumpAndSettle();
      expect(conversations.isSelectionModeActive, isFalse);
      expect(paintsShadow(), isFalse);
    }
    expect(tester.takeException(), isNull);
  });
}
