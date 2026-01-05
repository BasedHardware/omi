import 'dart:io';

import 'package:flutter/material.dart';
import 'package:omi/backend/preferences.dart';
import 'package:omi/providers/home_provider.dart';
import 'package:omi/utils/l10n_extensions.dart';
import 'package:provider/provider.dart';

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
    Key? key,
    required this.availableLanguages,
    this.selectedLanguage,
    this.selectedLanguageName,
    required this.languageScrollController,
    required this.onLanguageSelected,
  }) : super(key: key);

  @override
  State<LanguageSelectorWidget> createState() => _LanguageSelectorWidgetState();
}

class _LanguageSelectorWidgetState extends State<LanguageSelectorWidget> {
  late List<MapEntry<String, String>> languages;
  late List<MapEntry<String, String>> filteredLanguages;
  String searchQuery = '';
  String? currentSelectedLanguage;
  String? currentSelectedLanguageName;

  @override
  void initState() {
    super.initState();
    languages = widget.availableLanguages.entries.toList();
    filteredLanguages = List.from(languages);
    currentSelectedLanguage = widget.selectedLanguage;
    currentSelectedLanguageName = widget.selectedLanguageName;
  }

  void filterLanguages(String query) {
    debugPrint(query);
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
      debugPrint('Search query: $searchQuery, Found ${filteredLanguages.length} languages');
      for (var lang in filteredLanguages) {
        debugPrint('Filtered language: ${lang.key} (${lang.value})');
      }
    });
  }

  @override
  Widget build(BuildContext context) {
    return Container(
      height: MediaQuery.of(context).size.height * 0.7,
      padding: const EdgeInsets.all(16),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          Row(
            mainAxisAlignment: MainAxisAlignment.spaceBetween,
            textBaseline: TextBaseline.alphabetic,
            children: [
              Flexible(
                child: Text(
                  context.l10n.selectPrimaryLanguage,
                  maxLines: 2,
                  overflow: TextOverflow.ellipsis,
                  softWrap: true,
                  style: const TextStyle(
                    fontSize: 18,
                    fontWeight: FontWeight.bold,
                    color: Colors.white,
                  ),
                ),
              ),
              TextButton(
                onPressed: currentSelectedLanguage == null
                    ? null
                    : () {
                        widget.onLanguageSelected(
                          currentSelectedLanguage,
                          currentSelectedLanguageName,
                        );
                        Navigator.pop(context);
                      },
                child: Text(
                  context.l10n.done,
                  style: TextStyle(
                    color: currentSelectedLanguage == null ? null : Colors.white,
                  ),
                ),
              ),
            ],
          ),
          const SizedBox(height: 8),
          Text(
            context.l10n.languageBenefits,
            style: const TextStyle(
              fontSize: 14,
              color: Colors.grey,
            ),
          ),
          const SizedBox(height: 16),
          TextField(
            onChanged: filterLanguages,
            style: const TextStyle(color: Colors.white),
            autofocus: false,
            onSubmitted: (_) {}, // Prevent form submission on Enter
            decoration: InputDecoration(
              hintText: context.l10n.searchLanguageHint,
              hintStyle: const TextStyle(color: Colors.grey),
              prefixIcon: const Icon(Icons.search, color: Colors.grey),
              filled: true,
              fillColor: const Color(0xFF2A2A2A),
              border: OutlineInputBorder(
                borderRadius: BorderRadius.circular(8),
                borderSide: const BorderSide(color: Color(0xFF35343B)),
              ),
              enabledBorder: OutlineInputBorder(
                borderRadius: BorderRadius.circular(8),
                borderSide: const BorderSide(color: Color(0xFF35343B)),
              ),
              focusedBorder: OutlineInputBorder(
                borderRadius: BorderRadius.circular(8),
                borderSide: const BorderSide(color: Colors.deepPurple),
              ),
            ),
          ),
          const SizedBox(height: 16),
          Expanded(
            child: filteredLanguages.isEmpty
                ? Center(
                    child: Text(
                      context.l10n.noLanguagesFound,
                      style: const TextStyle(color: Colors.grey),
                    ),
                  )
                : ListView.builder(
                    controller: widget.languageScrollController,
                    key: ValueKey(searchQuery), // Force rebuild when search changes
                    itemCount: filteredLanguages.length,
                    itemBuilder: (context, index) {
                      final language = filteredLanguages[index];
                      final isSelected = currentSelectedLanguage == language.value;

                      return ListTile(
                        title: Text(
                          language.key,
                          style: const TextStyle(color: Colors.white),
                        ),
                        trailing: isSelected ? const Icon(Icons.check_circle, color: Colors.deepPurple) : null,
                        selected: isSelected,
                        selectedTileColor: Colors.deepPurple.withOpacity(0.2),
                        shape: RoundedRectangleBorder(
                          borderRadius: BorderRadius.circular(8),
                        ),
                        onTap: () {
                          setState(() {
                            if (currentSelectedLanguage == language.value) {
                              currentSelectedLanguage = null;
                              currentSelectedLanguageName = null;
                            } else {
                              currentSelectedLanguage = language.value;
                              currentSelectedLanguageName = language.key;
                            }
                          });
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

      debugPrint('Device locale: $deviceLocale, language code: $languageCode');

      // Try to find a matching language in available languages
      for (final entry in availableLanguages.entries) {
        final availableCode = entry.value.toLowerCase();
        // Match by language code (e.g., "en" matches "en", "ja" matches "ja")
        if (availableCode == languageCode || availableCode.startsWith('$languageCode-')) {
          setState(() {
            selectedLanguage = entry.value;
            selectedLanguageName = entry.key;
          });
          debugPrint('Auto-selected language: ${entry.key} (${entry.value})');
          return;
        }
      }
      debugPrint('No matching language found for device locale: $deviceLocale');
    } catch (e) {
      debugPrint('Error auto-detecting device language: $e');
    }
  }

  void _showLanguageSelector(BuildContext context, Map<String, String> availableLanguages) {
    showModalBottomSheet(
      context: context,
      backgroundColor: const Color(0xFF1A1A1A),
      shape: const RoundedRectangleBorder(
        borderRadius: BorderRadius.vertical(top: Radius.circular(20)),
      ),
      isScrollControlled: true,
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
  Widget build(BuildContext context) {
    return Column(
      children: [
        // Background area - takes remaining space
        Expanded(
          child: Container(), // Just takes up space for background image
        ),

        // Bottom drawer card - wraps content
        Container(
          width: double.infinity,
          padding: EdgeInsets.fromLTRB(32, 26, 32, MediaQuery.of(context).padding.bottom + 8),
          decoration: const BoxDecoration(
            color: Colors.black,
            borderRadius: BorderRadius.only(
              topLeft: Radius.circular(40),
              topRight: Radius.circular(40),
            ),
          ),
          child: SafeArea(
            top: false,
            child: Column(
              mainAxisSize: MainAxisSize.min,
              children: [
                const SizedBox(height: 16),

                // Main title
                Text(
                  context.l10n.whatsYourPrimaryLanguage,
                  style: const TextStyle(
                    color: Colors.white,
                    fontSize: 28,
                    fontWeight: FontWeight.bold,
                    height: 1.2,
                    fontFamily: 'Manrope',
                  ),
                  textAlign: TextAlign.center,
                ),

                const SizedBox(height: 28),

                // Language selection field
                InkWell(
                  onTap: () {
                    final homeProvider = Provider.of<HomeProvider>(context, listen: false);
                    _showLanguageSelector(context, homeProvider.availableLanguages);
                  },
                  child: Container(
                    decoration: BoxDecoration(
                      color: Colors.grey[900],
                      borderRadius: BorderRadius.circular(16),
                      border: Border.all(
                        color: Colors.grey[700]!,
                        width: 1,
                      ),
                    ),
                    padding: const EdgeInsets.symmetric(
                      horizontal: 24,
                      vertical: 20,
                    ),
                    child: Row(
                      mainAxisAlignment: MainAxisAlignment.center,
                      children: [
                        Text(
                          selectedLanguageName ?? context.l10n.selectYourLanguage,
                          style: TextStyle(
                            color: selectedLanguageName != null ? Colors.white : Colors.grey[500],
                            fontSize: 18,
                            fontFamily: 'Manrope',
                            fontWeight: FontWeight.w500,
                          ),
                        ),
                        const SizedBox(width: 12),
                        Icon(
                          Icons.keyboard_arrow_down,
                          color: Colors.grey[500],
                          size: 24,
                        ),
                      ],
                    ),
                  ),
                ),

                const SizedBox(height: 32),

                // Continue button
                SizedBox(
                  width: double.infinity,
                  height: 56,
                  child: ElevatedButton(
                    onPressed: selectedLanguage == null
                        ? null
                        : () async {
                            FocusManager.instance.primaryFocus?.unfocus();

                            // Update the user's primary language
                            final homeProvider = Provider.of<HomeProvider>(context, listen: false);
                            await homeProvider.updateUserPrimaryLanguage(selectedLanguage!);

                            widget.goNext();
                          },
                    style: ElevatedButton.styleFrom(
                      backgroundColor: selectedLanguage == null ? Colors.grey[800] : Colors.white,
                      foregroundColor: selectedLanguage == null ? Colors.grey[600] : Colors.black,
                      disabledBackgroundColor: Colors.grey[800],
                      disabledForegroundColor: Colors.grey[600],
                      shape: RoundedRectangleBorder(
                        borderRadius: BorderRadius.circular(28),
                      ),
                      elevation: 0,
                    ),
                    child: Text(
                      context.l10n.continueButton,
                      style: const TextStyle(
                        fontSize: 18,
                        fontWeight: FontWeight.w600,
                        fontFamily: 'Manrope',
                      ),
                    ),
                  ),
                ),

                // const SizedBox(height: 24),
              ],
            ),
          ),
        ),
      ],
    );
  }
}
