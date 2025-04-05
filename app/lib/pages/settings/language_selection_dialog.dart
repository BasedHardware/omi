import 'package:flutter/material.dart';
import 'package:flutter/cupertino.dart';
import 'package:omi/providers/capture_provider.dart';
import 'package:omi/providers/home_provider.dart';
import 'package:omi/utils/alerts/app_snackbar.dart';
import 'package:provider/provider.dart';
import 'dart:io';

class LanguageSelectionDialog {
  static Future<void> show(BuildContext context, {bool isRequired = false, bool forceShow = false}) async {
    final homeProvider = Provider.of<HomeProvider>(context, listen: false);

    // If the user has already set a primary language and it's not required or forced, don't show the dialog
    if (homeProvider.hasSetPrimaryLanguage && !isRequired && !forceShow) {
      return;
    }

    // If the user's primary language is empty, they haven't set one yet
    if (homeProvider.userPrimaryLanguage.isEmpty) {
      isRequired = true; // Make the dialog required if no language is set
    }

    // Use the availableLanguages directly as they're already ordered by popularity
    final languages = homeProvider.availableLanguages.entries.toList();

    // Preset the selected language if the user has one
    String? selectedLanguage = homeProvider.userPrimaryLanguage.isNotEmpty ? homeProvider.userPrimaryLanguage : null;
    String? selectedLanguageName = selectedLanguage != null
        ? homeProvider.availableLanguages.entries.firstWhere((element) => element.value == selectedLanguage).key
        : null;
    String searchQuery = '';
    List<MapEntry<String, String>> filteredLanguages = List.from(languages);
    final ScrollController _scrollController = ScrollController();

    // Function to scroll to the selected language
    void scrollToSelectedLanguage() {
      if (selectedLanguage != null) {
        final selectedIndex = filteredLanguages.indexWhere((lang) => lang.value == selectedLanguage);
        if (selectedIndex != -1 && _scrollController.hasClients) {
          _scrollController.animateTo(
            selectedIndex * 56.0, // Approximate height of each list item
            duration: const Duration(milliseconds: 300),
            curve: Curves.easeInOut,
          );
        }
      }
    }

    if (Platform.isIOS) {
      // iOS style picker with search
      await showCupertinoModalPopup(
        context: context,
        barrierDismissible: !isRequired,
        builder: (BuildContext context) {
          return StatefulBuilder(
            builder: (context, setState) {
              void filterLanguages(String query) {
                setState(() {
                  searchQuery = query.toLowerCase();
                  if (query.isEmpty) {
                    filteredLanguages = languages;
                  } else {
                    // Filter all languages
                    final filtered = languages.where((lang) {
                      return lang.key.toLowerCase().contains(searchQuery) ||
                          lang.value.toLowerCase().contains(searchQuery);
                    }).toList();

                    // Keep the original order from availableLanguages
                    filtered.sort((a, b) {
                      final aIndex = languages.indexOf(a);
                      final bIndex = languages.indexOf(b);
                      return aIndex.compareTo(bIndex);
                    });

                    filteredLanguages = filtered;
                  }
                });
              }

              return Container(
                height: 300,
                padding: const EdgeInsets.all(16),
                decoration: const BoxDecoration(
                  color: Color(0xFF1A1A1A),
                  borderRadius: BorderRadius.only(
                    topLeft: Radius.circular(20),
                    topRight: Radius.circular(20),
                  ),
                ),
                child: Column(
                  crossAxisAlignment: CrossAxisAlignment.start,
                  children: [
                    Row(
                      mainAxisAlignment: MainAxisAlignment.spaceBetween,
                      children: [
                        if (!isRequired)
                          CupertinoButton(
                            padding: EdgeInsets.zero,
                            child: const Text('Skip'),
                            onPressed: () {
                              Navigator.of(context).pop();
                            },
                          )
                        else
                          const SizedBox(width: 60),
                        const Text(
                          'Tell us your primary language',
                          style: TextStyle(
                            fontSize: 18,
                            fontWeight: FontWeight.bold,
                            color: Colors.white,
                          ),
                        ),
                        CupertinoButton(
                          padding: EdgeInsets.zero,
                          child: const Text('Done'),
                          onPressed: selectedLanguage == null
                              ? null
                              : () async {
                                  final success = await homeProvider.updateUserPrimaryLanguage(selectedLanguage!);
                                  if (success) {
                                    // Notify CaptureProvider to update recording settings
                                    Provider.of<CaptureProvider>(context, listen: false)
                                        .onRecordProfileSettingChanged();
                                    Navigator.of(context).pop();
                                    AppSnackbar.showSnackbarSuccess('Language set to $selectedLanguageName');
                                  } else {
                                    AppSnackbar.showSnackbarError('Failed to set language');
                                  }
                                },
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
                    CupertinoSearchTextField(
                      placeholder: 'Search language by name or code',
                      style: const TextStyle(color: Colors.white),
                      onChanged: filterLanguages,
                      backgroundColor: const Color(0xFF2A2A2A),
                      placeholderStyle: const TextStyle(color: Colors.grey),
                    ),
                    const SizedBox(height: 16),
                    // Auto-scroll to selected language when selection changes
                    if (selectedLanguage != null) 
                      Builder(builder: (context) {
                        WidgetsBinding.instance.addPostFrameCallback((_) {
                          scrollToSelectedLanguage();
                        });
                        return const SizedBox.shrink();
                      }),
                    Expanded(
                      child: filteredLanguages.isEmpty
                          ? const Center(
                              child: Text(
                                'No languages found',
                                style: TextStyle(color: Colors.grey),
                              ),
                            )
                          : CupertinoScrollbar(
                              child: ListView.builder(
                                controller: _scrollController,
                                key: PageStorageKey('language_list'),
                                itemCount: filteredLanguages.length,
                                itemBuilder: (context, index) {
                                  final language = filteredLanguages[index];
                                  final isSelected = selectedLanguage == language.value;

                                  return GestureDetector(
                                    onTap: () {
                                      setState(() {
                                        // Toggle selection - if already selected, unselect it
                                        if (selectedLanguage == language.value) {
                                          selectedLanguage = null;
                                          selectedLanguageName = null;
                                        } else {
                                          selectedLanguage = language.value;
                                          selectedLanguageName = language.key;
                                        }
                                      });
                                    },
                                    child: Container(
                                      padding: const EdgeInsets.symmetric(vertical: 12, horizontal: 8),
                                      decoration: BoxDecoration(
                                        border: Border(
                                          bottom: BorderSide(color: Colors.grey.shade800, width: 0.5),
                                        ),
                                        color: isSelected ? Colors.deepPurple.withOpacity(0.2) : Colors.transparent,
                                      ),
                                      child: Row(
                                        children: [
                                          Expanded(
                                            child: Column(
                                              crossAxisAlignment: CrossAxisAlignment.start,
                                              children: [
                                                Text(
                                                  language.key,
                                                  style: const TextStyle(
                                                    color: Colors.white,
                                                    fontSize: 16,
                                                  ),
                                                ),
                                              ],
                                            ),
                                          ),
                                          if (isSelected)
                                            const Icon(CupertinoIcons.check_mark, color: Colors.deepPurple),
                                        ],
                                      ),
                                    ),
                                  );
                                },
                              ),
                            ),
                    ),
                  ],
                ),
              );
            },
          );
        },
      );
    } else {
      // Android style dialog with search
      await showDialog(
        context: context,
        barrierDismissible: !isRequired,
        builder: (context) {
          return StatefulBuilder(
            builder: (context, setState) {
              void filterLanguages(String query) {
                setState(() {
                  searchQuery = query.toLowerCase();
                  if (query.isEmpty) {
                    filteredLanguages = languages;
                  } else {
                    // Filter all languages
                    final filtered = languages.where((lang) {
                      return lang.key.toLowerCase().contains(searchQuery) ||
                          lang.value.toLowerCase().contains(searchQuery);
                    }).toList();

                    // Keep the original order from availableLanguages
                    filtered.sort((a, b) {
                      final aIndex = languages.indexOf(a);
                      final bIndex = languages.indexOf(b);
                      return aIndex.compareTo(bIndex);
                    });

                    filteredLanguages = filtered;
                  }
                });
              }

              return AlertDialog(
                backgroundColor: const Color(0xFF1A1A1A),
                shape: RoundedRectangleBorder(borderRadius: BorderRadius.circular(16)),
                title: const Text(
                  'Tell us your primary language',
                  style: TextStyle(
                    color: Colors.white,
                    fontSize: 18,
                    fontWeight: FontWeight.bold,
                  ),
                ),
                content: SizedBox(
                  width: double.maxFinite,
                  height: 300,
                  child: Column(
                    mainAxisSize: MainAxisSize.min,
                    crossAxisAlignment: CrossAxisAlignment.start,
                    children: [
                      const Text(
                        'Set your language for sharper transcriptions and a personalized experience.',
                        style: TextStyle(
                          color: Colors.grey,
                          fontSize: 14,
                        ),
                      ),
                      const SizedBox(height: 16),
                      TextField(
                        onChanged: filterLanguages,
                        style: const TextStyle(color: Colors.white),
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
                                controller: _scrollController,
                                itemCount: filteredLanguages.length,
                                itemBuilder: (context, index) {
                                  final language = filteredLanguages[index];
                                  final isSelected = selectedLanguage == language.value;

                                  return ListTile(
                                    title: Text(
                                      language.key,
                                      style: const TextStyle(color: Colors.white),
                                    ),
                                    trailing:
                                        isSelected ? const Icon(Icons.check_circle, color: Colors.deepPurple) : null,
                                    selected: isSelected,
                                    selectedTileColor: Colors.deepPurple.withOpacity(0.2),
                                    shape: RoundedRectangleBorder(
                                      borderRadius: BorderRadius.circular(8),
                                    ),
                                    onTap: () {
                                      setState(() {
                                        // Toggle selection - if already selected, unselect it
                                        if (selectedLanguage == language.value) {
                                          selectedLanguage = null;
                                          selectedLanguageName = null;
                                        } else {
                                          selectedLanguage = language.value;
                                          selectedLanguageName = language.key;
                                        }
                                      });
                                    },
                                  );
                                },
                              ),
                      ),
                      // Auto-scroll to selected language when selection changes
                      if (selectedLanguage != null)
                        Builder(builder: (context) {
                          WidgetsBinding.instance.addPostFrameCallback((_) {
                            final selectedIndex =
                                filteredLanguages.indexWhere((lang) => lang.value == selectedLanguage);
                            if (selectedIndex != -1 && _scrollController.hasClients) {
                              _scrollController.animateTo(
                                selectedIndex * 56.0, // Approximate height of each list item
                                duration: const Duration(milliseconds: 300),
                                curve: Curves.easeInOut,
                              );
                            }
                          });
                          return const SizedBox.shrink();
                        }),
                    ],
                  ),
                ),
                actions: [
                  if (!isRequired)
                    TextButton(
                      onPressed: () {
                        Navigator.of(context).pop();
                      },
                      style: TextButton.styleFrom(
                        foregroundColor: Colors.grey,
                      ),
                      child: const Text('Skip'),
                    ),
                  ElevatedButton(
                    onPressed: selectedLanguage == null
                        ? null
                        : () async {
                            final success = await homeProvider.updateUserPrimaryLanguage(selectedLanguage!);
                            if (success) {
                              // Notify CaptureProvider to update recording settings
                              Provider.of<CaptureProvider>(context, listen: false).onRecordProfileSettingChanged();
                              Navigator.of(context).pop();
                              AppSnackbar.showSnackbarSuccess('Language set to $selectedLanguageName');
                            } else {
                              AppSnackbar.showSnackbarError('Failed to set language');
                            }
                          },
                    style: ElevatedButton.styleFrom(
                      backgroundColor: Colors.deepPurple,
                      disabledBackgroundColor: Colors.deepPurple.withOpacity(0.3),
                      foregroundColor: Colors.white,
                    ),
                    child: const Text('Confirm'),
                  ),
                ],
              );
            },
          );
        },
      );
    }
  }
}
