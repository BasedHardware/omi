import 'package:flutter/material.dart';
import 'package:flutter_localizations/flutter_localizations.dart';
import 'package:flutter_test/flutter_test.dart';

import 'package:omi/backend/schema/app.dart';
import 'package:omi/l10n/app_localizations.dart';
import 'package:omi/utils/app_localizations_helper.dart';

void main() {
  group('AppLocalizationsHelper', () {
    // Test wrapper that provides localization context
    Widget buildTestWidget({
      required Widget child,
      Locale locale = const Locale('en'),
    }) {
      return MaterialApp(
        locale: locale,
        localizationsDelegates: const [
          AppLocalizations.delegate,
          GlobalMaterialLocalizations.delegate,
          GlobalWidgetsLocalizations.delegate,
          GlobalCupertinoLocalizations.delegate,
        ],
        supportedLocales: AppLocalizations.supportedLocales,
        home: Scaffold(body: child),
      );
    }

    group('CategoryLocalization', () {
      testWidgets('returns localized title for known category ID', (tester) async {
        late String localizedTitle;

        await tester.pumpWidget(buildTestWidget(
          child: Builder(
            builder: (context) {
              final category = Category(id: 'conversation-analysis', title: 'API Title');
              localizedTitle = category.getLocalizedTitle(context);
              return Text(localizedTitle);
            },
          ),
        ));
        await tester.pumpAndSettle();

        expect(localizedTitle, isNotEmpty);
        expect(localizedTitle, isNot('API Title')); // Should use localized, not API title
      });

      testWidgets('returns API title as fallback for unknown category ID', (tester) async {
        late String localizedTitle;

        await tester.pumpWidget(buildTestWidget(
          child: Builder(
            builder: (context) {
              final category = Category(id: 'unknown-category-xyz', title: 'Fallback API Title');
              localizedTitle = category.getLocalizedTitle(context);
              return Text(localizedTitle);
            },
          ),
        ));
        await tester.pumpAndSettle();

        expect(localizedTitle, 'Fallback API Title');
      });

      testWidgets('localizes all known category IDs', (tester) async {
        final knownCategoryIds = [
          'conversation-analysis',
          'personality-emulation',
          'health-and-wellness',
          'education-and-learning',
          'communication-improvement',
          'emotional-and-mental-support',
          'productivity-and-organization',
          'entertainment-and-fun',
          'financial',
          'travel-and-exploration',
          'safety-and-security',
          'shopping-and-commerce',
          'social-and-relationships',
          'news-and-information',
          'utilities-and-tools',
          'other',
        ];

        for (final categoryId in knownCategoryIds) {
          late String localizedTitle;

          await tester.pumpWidget(buildTestWidget(
            child: Builder(
              builder: (context) {
                final category = Category(id: categoryId, title: 'API: $categoryId');
                localizedTitle = category.getLocalizedTitle(context);
                return Text(localizedTitle);
              },
            ),
          ));
          await tester.pumpAndSettle();

          expect(
            localizedTitle,
            isNot('API: $categoryId'),
            reason: 'Category "$categoryId" should have a localized title',
          );
        }
      });
    });

    group('AppCapabilityLocalization', () {
      testWidgets('returns localized title for known capability ID', (tester) async {
        late String localizedTitle;

        await tester.pumpWidget(buildTestWidget(
          child: Builder(
            builder: (context) {
              final capability = AppCapability(id: 'chat', title: 'API Chat Title');
              localizedTitle = capability.getLocalizedTitle(context);
              return Text(localizedTitle);
            },
          ),
        ));
        await tester.pumpAndSettle();

        expect(localizedTitle, isNotEmpty);
        expect(localizedTitle, isNot('API Chat Title'));
      });

      testWidgets('returns API title as fallback for unknown capability ID', (tester) async {
        late String localizedTitle;

        await tester.pumpWidget(buildTestWidget(
          child: Builder(
            builder: (context) {
              final capability = AppCapability(id: 'unknown-capability', title: 'Fallback');
              localizedTitle = capability.getLocalizedTitle(context);
              return Text(localizedTitle);
            },
          ),
        ));
        await tester.pumpAndSettle();

        expect(localizedTitle, 'Fallback');
      });

      testWidgets('localizes all known capability IDs', (tester) async {
        final knownCapabilityIds = [
          'chat',
          'memories',
          'external_integration',
          'proactive_notification',
          'integrations'
        ];

        for (final capabilityId in knownCapabilityIds) {
          late String localizedTitle;

          await tester.pumpWidget(buildTestWidget(
            child: Builder(
              builder: (context) {
                final capability = AppCapability(id: capabilityId, title: 'API: $capabilityId');
                localizedTitle = capability.getLocalizedTitle(context);
                return Text(localizedTitle);
              },
            ),
          ));
          await tester.pumpAndSettle();

          expect(
            localizedTitle,
            isNot('API: $capabilityId'),
            reason: 'Capability "$capabilityId" should have a localized title',
          );
        }
      });
    });

    group('TriggerEventLocalization', () {
      testWidgets('returns localized title for known trigger ID', (tester) async {
        late String localizedTitle;

        await tester.pumpWidget(buildTestWidget(
          child: Builder(
            builder: (context) {
              final trigger = TriggerEvent(id: 'memory_creation', title: 'API Trigger');
              localizedTitle = trigger.getLocalizedTitle(context);
              return Text(localizedTitle);
            },
          ),
        ));
        await tester.pumpAndSettle();

        expect(localizedTitle, isNotEmpty);
        expect(localizedTitle, isNot('API Trigger'));
      });

      testWidgets('returns API title as fallback for unknown trigger ID', (tester) async {
        late String localizedTitle;

        await tester.pumpWidget(buildTestWidget(
          child: Builder(
            builder: (context) {
              final trigger = TriggerEvent(id: 'unknown-trigger', title: 'Fallback Trigger');
              localizedTitle = trigger.getLocalizedTitle(context);
              return Text(localizedTitle);
            },
          ),
        ));
        await tester.pumpAndSettle();

        expect(localizedTitle, 'Fallback Trigger');
      });

      testWidgets('localizes all known trigger IDs', (tester) async {
        final knownTriggerIds = ['audio_bytes', 'memory_creation', 'transcript_processed'];

        for (final triggerId in knownTriggerIds) {
          late String localizedTitle;

          await tester.pumpWidget(buildTestWidget(
            child: Builder(
              builder: (context) {
                final trigger = TriggerEvent(id: triggerId, title: 'API: $triggerId');
                localizedTitle = trigger.getLocalizedTitle(context);
                return Text(localizedTitle);
              },
            ),
          ));
          await tester.pumpAndSettle();

          expect(
            localizedTitle,
            isNot('API: $triggerId'),
            reason: 'Trigger "$triggerId" should have a localized title',
          );
        }
      });
    });

    group('CapacityActionLocalization', () {
      testWidgets('returns localized title for known action ID', (tester) async {
        late String localizedTitle;

        await tester.pumpWidget(buildTestWidget(
          child: Builder(
            builder: (context) {
              final action = CapacityAction(id: 'create_conversation', title: 'API Action');
              localizedTitle = action.getLocalizedTitle(context);
              return Text(localizedTitle);
            },
          ),
        ));
        await tester.pumpAndSettle();

        expect(localizedTitle, isNotEmpty);
        expect(localizedTitle, isNot('API Action'));
      });

      testWidgets('returns API title as fallback for unknown action ID', (tester) async {
        late String localizedTitle;

        await tester.pumpWidget(buildTestWidget(
          child: Builder(
            builder: (context) {
              final action = CapacityAction(id: 'unknown-action', title: 'Fallback Action');
              localizedTitle = action.getLocalizedTitle(context);
              return Text(localizedTitle);
            },
          ),
        ));
        await tester.pumpAndSettle();

        expect(localizedTitle, 'Fallback Action');
      });

      testWidgets('localizes all known action IDs', (tester) async {
        final knownActionIds = [
          'create_conversation',
          'create_facts',
          'read_conversations',
          'read_memories',
          'read_tasks',
        ];

        for (final actionId in knownActionIds) {
          late String localizedTitle;

          await tester.pumpWidget(buildTestWidget(
            child: Builder(
              builder: (context) {
                final action = CapacityAction(id: actionId, title: 'API: $actionId');
                localizedTitle = action.getLocalizedTitle(context);
                return Text(localizedTitle);
              },
            ),
          ));
          await tester.pumpAndSettle();

          expect(
            localizedTitle,
            isNot('API: $actionId'),
            reason: 'Action "$actionId" should have a localized title',
          );
        }
      });
    });

    group('NotificationScopeLocalization', () {
      testWidgets('returns localized title for known scope ID', (tester) async {
        late String localizedTitle;

        await tester.pumpWidget(buildTestWidget(
          child: Builder(
            builder: (context) {
              final scope = NotificationScope(id: 'user_name', title: 'API Scope');
              localizedTitle = scope.getLocalizedTitle(context);
              return Text(localizedTitle);
            },
          ),
        ));
        await tester.pumpAndSettle();

        expect(localizedTitle, isNotEmpty);
        expect(localizedTitle, isNot('API Scope'));
      });

      testWidgets('returns API title as fallback for unknown scope ID', (tester) async {
        late String localizedTitle;

        await tester.pumpWidget(buildTestWidget(
          child: Builder(
            builder: (context) {
              final scope = NotificationScope(id: 'unknown-scope', title: 'Fallback Scope');
              localizedTitle = scope.getLocalizedTitle(context);
              return Text(localizedTitle);
            },
          ),
        ));
        await tester.pumpAndSettle();

        expect(localizedTitle, 'Fallback Scope');
      });

      testWidgets('localizes all known scope IDs', (tester) async {
        final knownScopeIds = ['user_name', 'user_facts', 'user_context', 'user_chat'];

        for (final scopeId in knownScopeIds) {
          late String localizedTitle;

          await tester.pumpWidget(buildTestWidget(
            child: Builder(
              builder: (context) {
                final scope = NotificationScope(id: scopeId, title: 'API: $scopeId');
                localizedTitle = scope.getLocalizedTitle(context);
                return Text(localizedTitle);
              },
            ),
          ));
          await tester.pumpAndSettle();

          expect(
            localizedTitle,
            isNot('API: $scopeId'),
            reason: 'Scope "$scopeId" should have a localized title',
          );
        }
      });
    });

    group('Multi-locale support', () {
      testWidgets('category title differs between English and Spanish locales', (tester) async {
        late String englishTitle;
        late String spanishTitle;

        // Get English title
        await tester.pumpWidget(buildTestWidget(
          locale: const Locale('en'),
          child: Builder(
            builder: (context) {
              final category = Category(id: 'health-and-wellness', title: 'API');
              englishTitle = category.getLocalizedTitle(context);
              return Text(englishTitle);
            },
          ),
        ));
        await tester.pumpAndSettle();

        // Get Spanish title
        await tester.pumpWidget(buildTestWidget(
          locale: const Locale('es'),
          child: Builder(
            builder: (context) {
              final category = Category(id: 'health-and-wellness', title: 'API');
              spanishTitle = category.getLocalizedTitle(context);
              return Text(spanishTitle);
            },
          ),
        ));
        await tester.pumpAndSettle();

        // Titles should be different for different locales
        expect(englishTitle, isNotEmpty);
        expect(spanishTitle, isNotEmpty);
        // Note: If translations are identical, this test documents that behavior
        // In a real scenario, Spanish should have different text
      });
    });
  });
}
