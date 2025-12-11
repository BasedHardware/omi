import 'dart:async';

import 'package:flutter/material.dart';
import 'package:omi/providers/capture_provider.dart';
import 'package:omi/providers/home_provider.dart';
import 'package:omi/providers/user_provider.dart';
import 'package:omi/utils/analytics/mixpanel.dart';
import 'package:provider/provider.dart';

class LanguageSettingsPage extends StatefulWidget {
  const LanguageSettingsPage({super.key});

  @override
  State<LanguageSettingsPage> createState() => _LanguageSettingsPageState();
}

class _LanguageSettingsPageState extends State<LanguageSettingsPage> {
  // Feature flag - set to true when vocabulary feature is ready
  static const bool _enableVocabulary = false;

  final TextEditingController _vocabularyController = TextEditingController();
  bool _isUpdatingLanguage = false;

  // Debounced deletion
  final Set<String> _pendingDeletions = {};
  Timer? _deletionDebounceTimer;
  bool _isDeletingBatch = false;

  @override
  void dispose() {
    _vocabularyController.dispose();
    _deletionDebounceTimer?.cancel();
    super.dispose();
  }

  Widget _buildSectionHeader(String title) {
    return Padding(
      padding: const EdgeInsets.only(left: 4, bottom: 8),
      child: Text(
        title.toUpperCase(),
        style: const TextStyle(
          color: Color(0xFF6B6B6B),
          fontSize: 12,
          fontWeight: FontWeight.w500,
          letterSpacing: 0.5,
        ),
      ),
    );
  }

  Widget _buildLanguageSelector(HomeProvider homeProvider) {
    final languageName = homeProvider.userPrimaryLanguage.isNotEmpty
        ? homeProvider.availableLanguages.entries
            .firstWhere(
              (element) => element.value == homeProvider.userPrimaryLanguage,
              orElse: () => const MapEntry('Not set', ''),
            )
            .key
        : 'Not set';

    return GestureDetector(
      onTap: _isUpdatingLanguage ? null : () => _showLanguageSelectionSheet(homeProvider),
      child: Container(
        decoration: BoxDecoration(
          color: const Color(0xFF1C1C1E),
          borderRadius: BorderRadius.circular(12),
        ),
        padding: const EdgeInsets.symmetric(horizontal: 16, vertical: 14),
        child: Row(
          children: [
            Expanded(
              child: Text(
                languageName,
                style: TextStyle(
                  color: _isUpdatingLanguage ? const Color(0xFF6B6B6B) : Colors.white,
                  fontSize: 16,
                  fontWeight: FontWeight.w400,
                ),
              ),
            ),
            if (_isUpdatingLanguage)
              const SizedBox(
                width: 16,
                height: 16,
                child: CircularProgressIndicator(
                  strokeWidth: 2,
                  valueColor: AlwaysStoppedAnimation<Color>(Color(0xFF6B6B6B)),
                ),
              )
            else
              const Icon(Icons.chevron_right, color: Color(0xFF6B6B6B), size: 20),
          ],
        ),
      ),
    );
  }

  void _showLanguageSelectionSheet(HomeProvider homeProvider) {
    final languages = homeProvider.availableLanguages;
    String currentLanguage = homeProvider.userPrimaryLanguage;

    showModalBottomSheet(
      context: context,
      backgroundColor: const Color(0xFF1C1C1E),
      shape: const RoundedRectangleBorder(
        borderRadius: BorderRadius.vertical(top: Radius.circular(16)),
      ),
      isScrollControlled: true,
      builder: (sheetContext) {
        return StatefulBuilder(
          builder: (context, setSheetState) {
            return DraggableScrollableSheet(
              initialChildSize: 0.7,
              minChildSize: 0.5,
              maxChildSize: 0.9,
              expand: false,
              builder: (context, scrollController) {
                return Column(
                  children: [
                    Container(
                      margin: const EdgeInsets.only(top: 12, bottom: 16),
                      width: 36,
                      height: 4,
                      decoration: BoxDecoration(
                        color: const Color(0xFF3C3C43),
                        borderRadius: BorderRadius.circular(2),
                      ),
                    ),
                    const Text(
                      'Select Language',
                      style: TextStyle(
                        color: Colors.white,
                        fontSize: 17,
                        fontWeight: FontWeight.w600,
                      ),
                    ),
                    const SizedBox(height: 16),
                    Expanded(
                      child: ListView.builder(
                        controller: scrollController,
                        itemCount: languages.length,
                        itemBuilder: (context, index) {
                          final entry = languages.entries.elementAt(index);
                          final isSelected = entry.value == currentLanguage;
                          return ListTile(
                            title: Text(
                              entry.key,
                              style: TextStyle(
                                color: isSelected ? Colors.white : const Color(0xFF8E8E93),
                                fontWeight: isSelected ? FontWeight.w500 : FontWeight.w400,
                              ),
                            ),
                            trailing: isSelected ? const Icon(Icons.check, color: Colors.white, size: 20) : null,
                            onTap: _isUpdatingLanguage
                                ? null
                                : () async {
                                    setSheetState(() {
                                      currentLanguage = entry.value;
                                    });
                                    Navigator.pop(sheetContext);
                                    setState(() {
                                      _isUpdatingLanguage = true;
                                    });
                                    try {
                                      await homeProvider.updateUserPrimaryLanguage(entry.value);
                                    } finally {
                                      if (mounted) {
                                        setState(() {
                                          _isUpdatingLanguage = false;
                                        });
                                      }
                                    }
                                  },
                          );
                        },
                      ),
                    ),
                  ],
                );
              },
            );
          },
        );
      },
    );
  }

  Widget _buildMultiLanguageToggle(UserProvider userProvider) {
    final isUpdating = userProvider.isUpdatingSingleLanguageMode;
    // Multi-language is ON when single_language_mode is OFF (inverted)
    final isMultiLanguageEnabled = !userProvider.singleLanguageMode;

    return Container(
      decoration: BoxDecoration(
        color: const Color(0xFF1C1C1E),
        borderRadius: BorderRadius.circular(12),
      ),
      padding: const EdgeInsets.symmetric(horizontal: 16, vertical: 14),
      child: Row(
        children: [
          const Expanded(
            child: Column(
              crossAxisAlignment: CrossAxisAlignment.start,
              children: [
                Text(
                  'Multi Language',
                  style: TextStyle(
                    color: Colors.white,
                    fontSize: 16,
                    fontWeight: FontWeight.w400,
                  ),
                ),
                SizedBox(height: 2),
                Text(
                  'Detect multiple languages & enable translation',
                  style: TextStyle(
                    color: Color(0xFF6B6B6B),
                    fontSize: 13,
                  ),
                ),
              ],
            ),
          ),
          if (isUpdating)
            const SizedBox(
              width: 24,
              height: 24,
              child: CircularProgressIndicator(
                strokeWidth: 2,
                valueColor: AlwaysStoppedAnimation<Color>(Colors.white),
              ),
            )
          else
            GestureDetector(
              onTap: () async {
                // Invert: Multi ON = single_language_mode OFF
                final success = await userProvider.setSingleLanguageMode(isMultiLanguageEnabled);
                if (success && context.mounted) {
                  // Fire and forget - don't block UI
                  context.read<CaptureProvider>().onTranscriptionSettingsChanged();
                }
              },
              child: Container(
                decoration: BoxDecoration(
                  color: isMultiLanguageEnabled ? const Color(0xFF007AFF) : Colors.transparent,
                  border: Border.all(
                    color: isMultiLanguageEnabled ? const Color(0xFF007AFF) : const Color(0xFF8E8E93),
                    width: 2,
                  ),
                  borderRadius: BorderRadius.circular(12),
                ),
                width: 24,
                height: 24,
                child: isMultiLanguageEnabled
                    ? const Icon(
                        Icons.check,
                        color: Colors.white,
                        size: 16,
                      )
                    : null,
              ),
            ),
        ],
      ),
    );
  }

  Widget _buildVocabularySection(UserProvider userProvider) {
    return Container(
      decoration: BoxDecoration(
        color: const Color(0xFF1C1C1E),
        borderRadius: BorderRadius.circular(12),
      ),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          Padding(
            padding: const EdgeInsets.all(16),
            child: Column(
              crossAxisAlignment: CrossAxisAlignment.start,
              children: [
                Row(
                  children: [
                    const Expanded(
                      child: Text(
                        'Custom Vocabulary',
                        style: TextStyle(
                          color: Colors.white,
                          fontSize: 16,
                          fontWeight: FontWeight.w400,
                        ),
                      ),
                    ),
                    Text(
                      '${userProvider.transcriptionVocabulary.length}/100',
                      style: const TextStyle(
                        color: Color(0xFF6B6B6B),
                        fontSize: 13,
                      ),
                    ),
                  ],
                ),
                const SizedBox(height: 4),
                const Text(
                  'Add words to improve transcription accuracy',
                  style: TextStyle(
                    color: Color(0xFF6B6B6B),
                    fontSize: 13,
                  ),
                ),
                const SizedBox(height: 16),
                Row(
                  children: [
                    Expanded(
                      child: TextField(
                        controller: _vocabularyController,
                        enabled: !(userProvider.isUpdatingVocabulary && !_isDeletingBatch),
                        style: const TextStyle(color: Colors.white, fontSize: 15),
                        decoration: InputDecoration(
                          hintText: 'e.g. omi, callie, nicky',
                          hintStyle: const TextStyle(color: Color(0xFF6B6B6B)),
                          filled: true,
                          fillColor: userProvider.isUpdatingVocabulary && !_isDeletingBatch
                              ? const Color(0xFF1A1A1A)
                              : const Color(0xFF2A2A2A),
                          border: OutlineInputBorder(
                            borderRadius: BorderRadius.circular(8),
                            borderSide: BorderSide.none,
                          ),
                          contentPadding: const EdgeInsets.symmetric(horizontal: 12, vertical: 12),
                        ),
                        onSubmitted: userProvider.isUpdatingVocabulary && !_isDeletingBatch
                            ? null
                            : (value) => _addWord(userProvider),
                      ),
                    ),
                    const SizedBox(width: 8),
                    GestureDetector(
                      onTap: userProvider.isUpdatingVocabulary ? null : () => _addWord(userProvider),
                      child: Container(
                        padding: const EdgeInsets.all(12),
                        decoration: BoxDecoration(
                          color: userProvider.isUpdatingVocabulary && !_isDeletingBatch
                              ? const Color(0xFF1A1A1A)
                              : const Color(0xFF2A2A2A),
                          borderRadius: BorderRadius.circular(8),
                        ),
                        child: userProvider.isUpdatingVocabulary && !_isDeletingBatch
                            ? const SizedBox(
                                width: 20,
                                height: 20,
                                child: CircularProgressIndicator(
                                  strokeWidth: 2,
                                  valueColor: AlwaysStoppedAnimation<Color>(Color(0xFF6B6B6B)),
                                ),
                              )
                            : const Icon(Icons.add, color: Colors.white, size: 20),
                      ),
                    ),
                  ],
                ),
              ],
            ),
          ),
          if (userProvider.transcriptionVocabulary.isNotEmpty) ...[
            const Divider(height: 1, color: Color(0xFF2A2A2A)),
            ListView.separated(
              shrinkWrap: true,
              physics: const NeverScrollableScrollPhysics(),
              itemCount: userProvider.transcriptionVocabulary.length,
              separatorBuilder: (_, __) => const Divider(height: 1, color: Color(0xFF2A2A2A)),
              itemBuilder: (context, index) {
                final word = userProvider.transcriptionVocabulary[index];
                final isPendingDelete = _pendingDeletions.contains(word);
                final isDisabled = _isDeletingBatch || userProvider.isUpdatingVocabulary;
                return Padding(
                  padding: const EdgeInsets.symmetric(horizontal: 16, vertical: 12),
                  child: Row(
                    children: [
                      Expanded(
                        child: Text(
                          word,
                          style: TextStyle(
                            color: isPendingDelete ? const Color(0xFF6B6B6B) : Colors.white,
                            fontSize: 15,
                          ),
                        ),
                      ),
                      if (isPendingDelete)
                        const SizedBox(
                          width: 20,
                          height: 20,
                          child: CircularProgressIndicator(
                            strokeWidth: 2,
                            valueColor: AlwaysStoppedAnimation<Color>(Color(0xFF6B6B6B)),
                          ),
                        )
                      else
                        GestureDetector(
                          onTap: isDisabled ? null : () => _queueWordDeletion(userProvider, word),
                          child: Icon(
                            Icons.close_sharp,
                            color: isDisabled ? const Color(0xFF3C3C3C) : const Color(0xFFFFFFFF),
                            size: 20,
                          ),
                        ),
                    ],
                  ),
                );
              },
            ),
          ],
        ],
      ),
    );
  }

  Future<void> _addWord(UserProvider userProvider) async {
    final input = _vocabularyController.text;
    if (input.trim().isEmpty) return;

    // Parse comma-separated words
    final words = input.split(',').map((w) => w.trim()).where((w) => w.isNotEmpty).toList();

    if (words.isEmpty) return;

    _vocabularyController.clear();

    // Add words one by one (provider handles duplicates and limit)
    bool anySuccess = false;
    for (final word in words) {
      final success = await userProvider.addVocabularyWord(word);
      if (success) anySuccess = true;
    }

    if (anySuccess && context.mounted) {
      // Fire and forget - don't block UI
      context.read<CaptureProvider>().onTranscriptionSettingsChanged();
    }
  }

  void _queueWordDeletion(UserProvider userProvider, String word) {
    setState(() {
      _pendingDeletions.add(word);
    });

    // Cancel existing timer and start new one (debounce)
    _deletionDebounceTimer?.cancel();
    _deletionDebounceTimer = Timer(const Duration(seconds: 1), () {
      _executeBatchDeletion(userProvider);
    });
  }

  Future<void> _executeBatchDeletion(UserProvider userProvider) async {
    if (_pendingDeletions.isEmpty) return;

    setState(() {
      _isDeletingBatch = true;
    });

    final wordsToDelete = List<String>.from(_pendingDeletions);
    bool anySuccess = false;

    for (final word in wordsToDelete) {
      final success = await userProvider.removeVocabularyWord(word);
      if (success) anySuccess = true;
    }

    if (mounted) {
      setState(() {
        _pendingDeletions.clear();
        _isDeletingBatch = false;
      });

      if (anySuccess) {
        context.read<CaptureProvider>().onTranscriptionSettingsChanged();
      }
    }
  }

  @override
  Widget build(BuildContext context) {
    MixpanelManager().pageOpened('Language Settings');

    return Scaffold(
      backgroundColor: Colors.black,
      appBar: AppBar(
        title: const Text(
          'Language',
          style: TextStyle(
            color: Colors.white,
            fontSize: 17,
            fontWeight: FontWeight.w600,
          ),
        ),
        centerTitle: true,
        backgroundColor: Colors.black,
        elevation: 0,
        iconTheme: const IconThemeData(color: Colors.white),
      ),
      body: Consumer2<HomeProvider, UserProvider>(
        builder: (context, homeProvider, userProvider, _) {
          return SingleChildScrollView(
            padding: const EdgeInsets.symmetric(horizontal: 16),
            child: Column(
              crossAxisAlignment: CrossAxisAlignment.start,
              children: [
                const SizedBox(height: 24),
                _buildSectionHeader('Primary Language'),
                _buildLanguageSelector(homeProvider),
                const SizedBox(height: 24),
                _buildSectionHeader('Transcription'),
                _buildMultiLanguageToggle(userProvider),
                if (_enableVocabulary) ...[
                  const SizedBox(height: 24),
                  _buildSectionHeader('Vocabulary'),
                  _buildVocabularySection(userProvider),
                ],
                const SizedBox(height: 32),
              ],
            ),
          );
        },
      ),
    );
  }
}
