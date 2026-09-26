import 'dart:async';
import 'dart:io';

import 'package:flutter/material.dart';

import 'package:provider/provider.dart';

import 'package:omi/backend/preferences.dart';
import 'package:omi/providers/home_provider.dart';
import 'package:omi/providers/user_provider.dart';
import 'package:omi/pages/onboarding/widgets/onboarding_card.dart';
import 'package:omi/ui/ui.dart';
import 'package:omi/utils/l10n_extensions.dart';
import 'package:omi/utils/language_autonyms.dart';
import 'package:omi/utils/logger.dart';

class PrimaryLanguageWidget extends StatefulWidget {
  final Function goNext;

  const PrimaryLanguageWidget({super.key, required this.goNext});

  @override
  State<PrimaryLanguageWidget> createState() => _PrimaryLanguageWidgetState();
}

class _PrimaryLanguageWidgetState extends State<PrimaryLanguageWidget> {
  String? selectedLanguage;
  String? selectedLanguageName;
  String _query = '';

  /// The language chosen for the person before they touch the list (saved, or the device's),
  /// shown first so the check is on screen. A tap does not reorder the list under the finger.
  String? _suggested;

  @override
  void initState() {
    super.initState();
    // Initialize with the user's saved primary language if available, or auto-detect from device
    WidgetsBinding.instance.addPostFrameCallback((_) {
      final savedLanguage = SharedPreferencesUtil().userPrimaryLanguage;
      final homeProvider = Provider.of<HomeProvider>(context, listen: false);

      if (savedLanguage.isNotEmpty) {
        setState(() {
          selectedLanguage = savedLanguage;
          _suggested = savedLanguage;
          // Find the language name for the saved language code
          try {
            selectedLanguageName =
                homeProvider.availableLanguages.entries.firstWhere((entry) => entry.value == savedLanguage).key;
          } catch (e) {
            // If language not found in the map, just use the code
            selectedLanguageName = savedLanguage;
          }
        });
      } else {
        // Auto-detect from device system language
        _autoSelectDeviceLanguage(homeProvider.availableLanguages);
      }
    });
  }

  void _autoSelectDeviceLanguage(Map<String, String> availableLanguages) {
    try {
      // Get device locale (e.g., "en_US", "ja_JP", "zh_CN")
      final deviceLocale = Platform.localeName;
      final languageCode = deviceLocale.split('_').first.toLowerCase();

      Logger.debug('Device locale: $deviceLocale, language code: $languageCode');

      // Try to find a matching language in available languages
      for (final entry in availableLanguages.entries) {
        final availableCode = entry.value.toLowerCase();
        // Match by language code (e.g., "en" matches "en", "ja" matches "ja")
        if (availableCode == languageCode || availableCode.startsWith('$languageCode-')) {
          setState(() {
            selectedLanguage = entry.value;
            selectedLanguageName = entry.key;
            _suggested = entry.value;
          });
          Logger.debug('Auto-selected language: ${entry.key} (${entry.value})');
          return;
        }
      }
      Logger.debug('No matching language found for device locale: $deviceLocale');
    } catch (e) {
      Logger.debug('Error auto-detecting device language: $e');
    }
  }

  Future<void> _continue() async {
    FocusManager.instance.primaryFocus?.unfocus();
    final homeProvider = Provider.of<HomeProvider>(context, listen: false);
    final userProvider = Provider.of<UserProvider>(context, listen: false);
    final success = await homeProvider.updateUserPrimaryLanguage(selectedLanguage!, userProvider: userProvider);
    if (!mounted) return;
    if (!success) {
      OmiHaptics.error();
      OmiFeedback.error(
        context,
        context.l10n.failedToSetLanguage,
        actionLabel: context.l10n.tryAgain,
        onAction: () => unawaited(_continue()),
      );
      return;
    }
    OmiHaptics.selection();
    widget.goNext();
  }

  /// Name → code pairs matching the search, the suggested language first.
  List<MapEntry<String, String>> _visibleLanguages(Map<String, String> available) {
    final query = _query.trim().toLowerCase();
    final matches = available.entries.where((language) {
      if (query.isEmpty) return true;
      final autonym = languageAutonym(language.value)?.toLowerCase() ?? '';
      return language.key.toLowerCase().contains(query) ||
          language.value.toLowerCase().contains(query) ||
          autonym.contains(query);
    }).toList();
    final suggested = matches.indexWhere((language) => language.value == _suggested);
    if (suggested > 0) matches.insert(0, matches.removeAt(suggested));
    return matches;
  }

  void _select(MapEntry<String, String> language) {
    OmiHaptics.selection();
    setState(() {
      selectedLanguage = language.value;
      selectedLanguageName = language.key;
    });
  }

  @override
  Widget build(BuildContext context) {
    final l10n = context.l10n;
    final languages = _visibleLanguages(context.watch<HomeProvider>().availableLanguages);
    return OnboardingStep(
      card: OnboardingCard(
        content: [
          OnboardingHeader(title: l10n.whatLanguageDoYouSpeakMost, subtitle: l10n.languageOnboardingSubtitle),
          const SizedBox(height: OmiSpacing.md),
          OmiSearchField(placeholder: l10n.searchLanguages, onChanged: (value) => setState(() => _query = value)),
          const SizedBox(height: OmiSpacing.sm),
          if (languages.isEmpty)
            Padding(
              padding: const EdgeInsets.symmetric(vertical: OmiSpacing.xl),
              child: Center(child: Text(l10n.noLanguagesFound, style: OmiType.subhead)),
            )
          else
            // v2: one grouped card; each row is the language in its own script over its English name.
            Container(
              decoration: BoxDecoration(color: OmiColors.surface1, borderRadius: OmiRadius.rowAll),
              child: Column(
                children: [
                  for (final (i, language) in languages.indexed) ...[
                    if (i > 0) Divider(height: 0.5, thickness: 0.5, indent: OmiSpacing.md, color: OmiColors.border),
                    _LanguageRow(
                      key: ValueKey('onboarding_language_${language.value}'),
                      name: language.key,
                      autonym: languageAutonym(language.value),
                      selected: language.value == selectedLanguage,
                      onTap: () => _select(language),
                    ),
                  ],
                ],
              ),
            ),
        ],
        footer: [
          const SizedBox(height: OmiSpacing.md),
          // Async: the button shows a spinner and ignores taps while the language saves.
          OmiButton(
            key: const Key('onboarding_language_continue'),
            label: l10n.continueButton,
            expand: true,
            onPressed: selectedLanguage == null ? null : _continue,
          ),
        ],
      ),
    );
  }
}

class _LanguageRow extends StatelessWidget {
  const _LanguageRow(
      {super.key, required this.name, required this.autonym, required this.selected, required this.onTap});

  /// The English name ("Spanish (Latin America)").
  final String name;

  /// The name in the language's own script, when known.
  final String? autonym;
  final bool selected;
  final VoidCallback onTap;

  @override
  Widget build(BuildContext context) {
    final primary = autonym ?? name;
    return Semantics(
      button: true,
      selected: selected,
      label: autonym == null || autonym == name ? name : '$primary, $name',
      excludeSemantics: true,
      onTap: onTap,
      child: InkWell(
        onTap: onTap,
        child: ConstrainedBox(
          constraints: const BoxConstraints(minHeight: 52),
          child: Padding(
            padding: const EdgeInsets.symmetric(horizontal: OmiSpacing.md, vertical: OmiSpacing.sm),
            child: Row(
              children: [
                Expanded(
                  child: Column(
                    crossAxisAlignment: CrossAxisAlignment.start,
                    mainAxisSize: MainAxisSize.min,
                    children: [
                      Text(primary, style: OmiType.body),
                      if (autonym != null) Text(name, style: OmiType.footnote.copyWith(color: OmiColors.textSecondary)),
                    ],
                  ),
                ),
                if (selected) OmiGlyph(OmiGlyphs.checkmark, size: 17, color: OmiColors.textPrimary),
              ],
            ),
          ),
        ),
      ),
    );
  }
}
