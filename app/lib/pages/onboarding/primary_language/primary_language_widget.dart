import 'package:flutter/material.dart';
import 'package:gradient_borders/gradient_borders.dart';
import 'package:intercom_flutter/intercom_flutter.dart';
import 'package:omi/backend/preferences.dart';
import 'package:omi/providers/home_provider.dart';
import 'package:omi/utils/platform/platform_service.dart';
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
              const Flexible(
                child: Text(
                  'Select your primary language',
                  maxLines: 2,
                  overflow: TextOverflow.ellipsis,
                  softWrap: true,
                  style: TextStyle(
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
                  'Done',
                  style: TextStyle(
                    color: currentSelectedLanguage == null ? null : Colors.white,
                  ),
                ),
              ),
            ],
          ),
          const SizedBox(height: 8),
          const Text(
            'Set your language for sharper transcriptions and a personalized experience',
            style: TextStyle(
              fontSize: 14,
              color: Colors.grey,
            ),
          ),
          const SizedBox(height: 16),
          TextField(
            onChanged: filterLanguages,
            style: const TextStyle(color: Colors.white),
            autofocus: true,
            onSubmitted: (_) {}, // Prevent form submission on Enter
            decoration: InputDecoration(
              hintText: 'Search language by name or code',
              hintStyle: const TextStyle(color: Colors.grey),
              prefixIcon: const Icon(Icons.search, color: Colors.grey),
              filled: true,
              fillColor: const Color(0xFF2A2A2A),
              border: OutlineInputBorder(
                borderRadius: BorderRadius.circular(8),
                borderSide: BorderSide(color: Color(0xFF35343B)),
              ),
              enabledBorder: OutlineInputBorder(
                borderRadius: BorderRadius.circular(8),
                borderSide: BorderSide(color: Color(0xFF35343B)),
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
                ? const Center(
                    child: Text(
                      'No languages found',
                      style: TextStyle(color: Colors.grey),
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
    // Initialize with the user's saved primary language if available
    WidgetsBinding.instance.addPostFrameCallback((_) {
      final savedLanguage = SharedPreferencesUtil().userPrimaryLanguage;
      if (savedLanguage.isNotEmpty) {
        setState(() {
          selectedLanguage = savedLanguage;
          // Find the language name for the saved language code
          final homeProvider = Provider.of<HomeProvider>(context, listen: false);
          try {
            selectedLanguageName = homeProvider.availableLanguages.entries.firstWhere((entry) => entry.value == savedLanguage).key;
          } catch (e) {
            // If language not found in the map, just use the code
            selectedLanguageName = savedLanguage;
          }
        });
      }
    });
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
                const Text(
                  'What\'s your primary language?',
                  style: TextStyle(
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
                          selectedLanguageName ?? 'Select your language',
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
                    child: const Text(
                      'Continue',
                      style: TextStyle(
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
