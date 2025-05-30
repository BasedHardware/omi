import 'package:flutter/material.dart';
import 'package:gradient_borders/gradient_borders.dart';
import 'package:intercom_flutter/intercom_flutter.dart';
import 'package:omi/backend/preferences.dart';
import 'package:omi/providers/home_provider.dart';
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
                onPressed: () {
                  if (currentSelectedLanguage != null) {
                    widget.onLanguageSelected(
                      currentSelectedLanguage,
                      currentSelectedLanguageName,
                    );
                  }
                  Navigator.pop(context);
                },
                child: Text(
                  'Done',
                  style: TextStyle(
                    color:
                        currentSelectedLanguage == null ? null : Colors.white,
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
                borderSide: BorderSide(color: Colors.grey.shade800),
              ),
              enabledBorder: OutlineInputBorder(
                borderRadius: BorderRadius.circular(8),
                borderSide: BorderSide(color: Colors.grey.shade800),
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

  @override
  void dispose() {
    _languageScrollController.dispose();
    super.dispose();
  }

  void _showLanguageSelector(BuildContext context, Map<String, String> availableLanguages) {
    try {
      showModalBottomSheet(
      context: context,
      backgroundColor: const Color(0xFF1A1A1A),
      shape: const RoundedRectangleBorder(
        borderRadius: BorderRadius.vertical(top: Radius.circular(20)),
      ),
      isScrollControlled: true,
      isDismissible: true,
      enableDrag: true,
      barrierColor: Colors.black.withOpacity(0.5)
      builder: (context) {
        return WillPopScope(
          onWillPop: () async {
            Navigator.pop(context);
            return true;
          },
          child: LanguageSelectorWidget(
            availableLanguages: availableLanguages,
            selectedLanguage: selectedLanguage,
            selectedLanguageName: selectedLanguageName,
            languageScrollController: _languageScrollController,
            onLanguageSelected: (language, name) {
              setState(() {
                selectedLanguage = language;
                selectedLanguageName = name;
              });
              Navigator.pop(context);
            },
          ),
        );
      },
    ).catchError((error) {
      debugPrint('Error showing language selector: $error');
      ScaffoldMessenger.of(context).showSnackBar(
        const SnackBar(
          content: Text('Error showing language selector. Please try again.'),
        ),
        );
      });
    } catch (e) {
      debugPrint('Error in _showLanguageSelector: $e');
      ScaffoldMessenger.of(context).showSnackBar(
        const SnackBar(
          content: Text('An error occurred. Please try again.'),
        ),
      );
    }
  }

  @override
  Widget build(BuildContext context) {
    return Padding(
      padding: const EdgeInsets.symmetric(horizontal: 16),
      child: Column(
        mainAxisAlignment: MainAxisAlignment.end,
        crossAxisAlignment: CrossAxisAlignment.center,
        children: [
          Align(
            alignment: Alignment.topRight,
            child: IconButton(
              icon: const Icon(Icons.close, color: Colors.white),
              onPressed: () => Navigator.pop(context),
            ),
          ),
          Text(
            'Tell us your Primary Language',
            style: TextStyle(color: Colors.grey.shade300, fontSize: 16),
            textAlign: TextAlign.start,
          ),
          const SizedBox(height: 24),
          InkWell(
            onTap: () {
              final homeProvider = Provider.of<HomeProvider>(context, listen: false);
              _showLanguageSelector(context, homeProvider.availableLanguages);
            },
            child: Container(
              width: double.infinity,
              padding: const EdgeInsets.symmetric(vertical: 18),
              decoration: BoxDecoration(
                borderRadius: BorderRadius.circular(8),
                border: GradientBoxBorder(
                  gradient: const LinearGradient(
                    colors: <Color>[
                      Color.fromARGB(255, 202, 201, 201),
                      Color.fromARGB(255, 159, 158, 158),
                    ],
                  ),
                  width: 1,
                ),
              ),
              child: Row(
                mainAxisAlignment: MainAxisAlignment.center,
                children: [
                  Text(
                    selectedLanguageName ?? 'Select language',
                    style: TextStyle(
                      fontSize: 16,
                      color: Colors.grey.shade200,
                    ),
                  ),
                ],
              ),
            ),
          ),
          const SizedBox(height: 20),
          Row(
            children: [
              Expanded(
                child: Container(
                  width: double.infinity,
                  decoration: BoxDecoration(
                    border: const GradientBoxBorder(
                      gradient: LinearGradient(colors: [Color.fromARGB(127, 208, 208, 208), Color.fromARGB(127, 188, 99, 121), Color.fromARGB(127, 86, 101, 182), Color.fromARGB(127, 126, 190, 236)]),
                      width: 2,
                    ),
                    borderRadius: BorderRadius.circular(12),
                  ),
                  child: MaterialButton(
                    padding: const EdgeInsets.symmetric(horizontal: 32, vertical: 16),
                    onPressed: () async {
                      if (selectedLanguage == null) {
                        ScaffoldMessenger.of(context).showSnackBar(
                          const SnackBar(content: Text('Please select your primary language')),
                        );
                      } else {
                        FocusManager.instance.primaryFocus?.unfocus();

                        // Update the user's primary language
                        final homeProvider = Provider.of<HomeProvider>(context, listen: false);
                        await homeProvider.updateUserPrimaryLanguage(selectedLanguage!);

                        widget.goNext();
                      }
                    },
                    child: const Text(
                      'Continue',
                      style: TextStyle(
                        decoration: TextDecoration.none,
                      ),
                    ),
                  ),
                ),
              )
            ],
          ),
          const SizedBox(
            height: 12,
          ),
          InkWell(
            child: Text(
              'Need Help?',
              style: TextStyle(
                color: Colors.grey.shade300,
                decoration: TextDecoration.underline,
              ),
            ),
            onTap: () {
              Intercom.instance.displayMessenger();
            },
          ),
        ],
      ),
    );
  }
}
