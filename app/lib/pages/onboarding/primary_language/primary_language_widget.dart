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
import 'package:omi/utils/logger.dart';

class PrimaryLanguageWidget extends StatefulWidget {
  final Function goNext;

  const PrimaryLanguageWidget({super.key, required this.goNext});

  @override
  State<PrimaryLanguageWidget> createState() => _PrimaryLanguageWidgetState();
}

class LanguageSelectorWidget extends StatefulWidget {
  final Map<String, String> availableLanguages;
  final String? selectedLanguage;
  final String? selectedLanguageName;
  final ScrollController languageScrollController;
  final Function(String?, String?) onLanguageSelected;

  const LanguageSelectorWidget({
    super.key,
    required this.availableLanguages,
    this.selectedLanguage,
    this.selectedLanguageName,
    required this.languageScrollController,
    required this.onLanguageSelected,
  });

  @override
  State<LanguageSelectorWidget> createState() => _LanguageSelectorWidgetState();
}

class _LanguageSelectorWidgetState extends State<LanguageSelectorWidget> {
  late List<MapEntry<String, String>> languages;
  late List<MapEntry<String, String>> filteredLanguages;
  String searchQuery = '';
  String? currentSelectedLanguage;

  @override
  void initState() {
    super.initState();
    languages = widget.availableLanguages.entries.toList();
    filteredLanguages = List.from(languages);
    currentSelectedLanguage = widget.selectedLanguage;
  }

  void filterLanguages(String query) {
    Logger.debug(query);
    setState(() {
      searchQuery = query.toLowerCase();
      if (query.isEmpty) {
        filteredLanguages = List.from(languages);
      } else {
        filteredLanguages = languages.where((lang) {
          return lang.key.toLowerCase().contains(searchQuery) || lang.value.toLowerCase().contains(searchQuery);
        }).toList();
      }

      // Debug print to verify filtering
      Logger.debug('Search query: $searchQuery, Found ${filteredLanguages.length} languages');
      for (var lang in filteredLanguages) {
        Logger.debug('Filtered language: ${lang.key} (${lang.value})');
      }
    });
  }

  @override
  Widget build(BuildContext context) {
    return SizedBox(
      height: MediaQuery.sizeOf(context).height * 0.7,
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.stretch,
        children: [
          Text(context.l10n.languageBenefits, style: OmiType.footnote.copyWith(color: OmiColors.textSecondary)),
          const SizedBox(height: OmiSpacing.md),
          OmiSearchField(placeholder: context.l10n.searchLanguageHint, onChanged: filterLanguages),
          const SizedBox(height: OmiSpacing.md),
          Expanded(
            child: filteredLanguages.isEmpty
                ? OmiEmptyState(icon: Icons.translate, title: context.l10n.noLanguagesFound)
                : ListView.builder(
                    controller: widget.languageScrollController,
                    key: ValueKey(searchQuery), // Force rebuild when search changes
                    itemCount: filteredLanguages.length,
                    itemBuilder: (context, index) {
                      final language = filteredLanguages[index];
                      final isSelected = currentSelectedLanguage == language.value;
                      return ListTile(
                        title: Text(language.key, style: OmiType.body),
                        trailing: isSelected ? const Icon(Icons.check_circle, color: OmiColors.accent) : null,
                        selected: isSelected,
                        selectedTileColor: OmiColors.surface2,
                        shape: const RoundedRectangleBorder(borderRadius: OmiRadius.smAll),
                        // Picking a language is the answer: it selects and closes the picker.
                        onTap: () {
                          OmiHaptics.selection();
                          widget.onLanguageSelected(language.value, language.key);
                          Navigator.of(context).pop();
                        },
                      );
                    },
                  ),
          ),
        ],
      ),
    );
  }
}

class _PrimaryLanguageWidgetState extends State<PrimaryLanguageWidget> {
  String? selectedLanguage;
  String? selectedLanguageName;
  final ScrollController _languageScrollController = ScrollController();

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

  void _showLanguageSelector(BuildContext context, Map<String, String> availableLanguages) {
    showOmiSheet<void>(
      context: context,
      title: context.l10n.selectPrimaryLanguage,
      builder: (context) {
        return LanguageSelectorWidget(
          availableLanguages: availableLanguages,
          selectedLanguage: selectedLanguage,
          selectedLanguageName: selectedLanguageName,
          languageScrollController: _languageScrollController,
          onLanguageSelected: (language, name) {
            setState(() {
              selectedLanguage = language;
              selectedLanguageName = name;
            });
          },
        );
      },
    );
  }

  @override
  void dispose() {
    _languageScrollController.dispose();
    super.dispose();
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

  @override
  Widget build(BuildContext context) {
    final hasSelection = selectedLanguageName != null;
    return OnboardingStep(
      card: OnboardingCard(
        content: [
          Semantics(
            header: true,
            child: Text(context.l10n.whatsYourPrimaryLanguage, style: OmiType.title1, textAlign: TextAlign.center),
          ),
          const SizedBox(height: OmiSpacing.xxl),
          Semantics(
            button: true,
            label: context.l10n.selectPrimaryLanguage,
            value: selectedLanguageName,
            excludeSemantics: true,
            child: Material(
              color: OmiColors.surface1,
              shape: const RoundedRectangleBorder(
                borderRadius: OmiRadius.lgAll,
                side: BorderSide(color: OmiColors.border),
              ),
              child: InkWell(
                customBorder: const RoundedRectangleBorder(borderRadius: OmiRadius.lgAll),
                onTap: () {
                  final homeProvider = Provider.of<HomeProvider>(context, listen: false);
                  _showLanguageSelector(context, homeProvider.availableLanguages);
                },
                child: Padding(
                  padding: const EdgeInsets.symmetric(horizontal: OmiSpacing.xl, vertical: OmiSpacing.lg),
                  child: Row(
                    mainAxisAlignment: MainAxisAlignment.center,
                    children: [
                      Flexible(
                        child: Text(
                          selectedLanguageName ?? context.l10n.selectYourLanguage,
                          style: OmiType.body.copyWith(
                            color: hasSelection ? OmiColors.textPrimary : OmiColors.textTertiary,
                            fontWeight: FontWeight.w500,
                          ),
                        ),
                      ),
                      const SizedBox(width: OmiSpacing.sm),
                      const Icon(Icons.keyboard_arrow_down, color: OmiColors.textTertiary, size: 24),
                    ],
                  ),
                ),
              ),
            ),
          ),
        ],
        footer: [
          const SizedBox(height: OmiSpacing.xxl),
          // Async: the button shows a spinner and ignores taps while the language saves.
          OmiButton(
            key: const Key('onboarding_language_continue'),
            label: context.l10n.continueButton,
            expand: true,
            onPressed: selectedLanguage == null ? null : _continue,
          ),
        ],
      ),
    );
  }
}
