import 'dart:async';

import 'package:flutter/material.dart';
import 'package:font_awesome_flutter/font_awesome_flutter.dart';
import 'package:omi/providers/capture_provider.dart';
import 'package:omi/providers/user_provider.dart';
import 'package:omi/utils/analytics/mixpanel.dart';
import 'package:provider/provider.dart';

class CustomVocabularyPage extends StatefulWidget {
  const CustomVocabularyPage({super.key});

  @override
  State<CustomVocabularyPage> createState() => _CustomVocabularyPageState();
}

class _CustomVocabularyPageState extends State<CustomVocabularyPage> {
  final TextEditingController _vocabularyController = TextEditingController();

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

  Widget _buildVocabularyCard(UserProvider userProvider) {
    final isDisabled = _isDeletingBatch || userProvider.isUpdatingVocabulary;

    return Container(
      padding: const EdgeInsets.all(16),
      decoration: BoxDecoration(
        color: const Color(0xFF1C1C1E),
        borderRadius: BorderRadius.circular(14),
      ),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          // Header row with icon
          Row(
            children: [
              Container(
                width: 40,
                height: 40,
                decoration: BoxDecoration(
                  color: const Color(0xFF2A2A2E),
                  borderRadius: BorderRadius.circular(10),
                ),
                child: Center(
                  child: FaIcon(
                    FontAwesomeIcons.book,
                    color: Colors.grey.shade400,
                    size: 16,
                  ),
                ),
              ),
              const SizedBox(width: 14),
              Expanded(
                child: Column(
                  crossAxisAlignment: CrossAxisAlignment.start,
                  children: [
                    Row(
                      children: [
                        const Text(
                          'Add Words',
                          style: TextStyle(
                            color: Colors.white,
                            fontSize: 16,
                            fontWeight: FontWeight.w500,
                          ),
                        ),
                        const SizedBox(width: 8),
                        Container(
                          padding: const EdgeInsets.symmetric(horizontal: 8, vertical: 4),
                          decoration: BoxDecoration(
                            color: Colors.grey.shade800,
                            borderRadius: BorderRadius.circular(8),
                          ),
                          child: Text(
                            '${userProvider.transcriptionVocabulary.length}',
                            style: const TextStyle(
                              color: Colors.grey,
                              fontSize: 11,
                              fontWeight: FontWeight.w500,
                            ),
                          ),
                        ),
                      ],
                    ),
                    const SizedBox(height: 2),
                    Text(
                      'Names, terms, or uncommon words',
                      style: TextStyle(
                        color: Colors.grey.shade500,
                        fontSize: 13,
                      ),
                    ),
                  ],
                ),
              ),
            ],
          ),
          const SizedBox(height: 20),

          // Input field
          Row(
            children: [
              Expanded(
                child: Container(
                  decoration: BoxDecoration(
                    color: const Color(0xFF2C2C2E),
                    borderRadius: BorderRadius.circular(10),
                  ),
                  child: TextField(
                    controller: _vocabularyController,
                    enabled: !(userProvider.isUpdatingVocabulary && !_isDeletingBatch),
                    style: const TextStyle(color: Colors.white, fontSize: 15),
                    decoration: InputDecoration(
                      hintText: 'Omi, Callie, OpenAI',
                      hintStyle: TextStyle(color: Colors.grey.shade600, fontSize: 14),
                      contentPadding: const EdgeInsets.symmetric(horizontal: 16, vertical: 14),
                      border: InputBorder.none,
                      enabledBorder: InputBorder.none,
                      focusedBorder: OutlineInputBorder(
                        borderRadius: BorderRadius.circular(10),
                        borderSide: const BorderSide(color: Colors.white24, width: 1),
                      ),
                    ),
                    onSubmitted: userProvider.isUpdatingVocabulary && !_isDeletingBatch
                        ? null
                        : (value) => _addWord(userProvider),
                  ),
                ),
              ),
              const SizedBox(width: 12),
              GestureDetector(
                onTap: userProvider.isUpdatingVocabulary ? null : () => _addWord(userProvider),
                child: Container(
                  padding: const EdgeInsets.all(14),
                  decoration: BoxDecoration(
                    color: userProvider.isUpdatingVocabulary && !_isDeletingBatch
                        ? const Color(0xFF1A1A1A)
                        : const Color(0xFF2A2A2E),
                    borderRadius: BorderRadius.circular(10),
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
                      : const FaIcon(FontAwesomeIcons.plus, color: Colors.white, size: 16),
                ),
              ),
            ],
          ),

          // Words chips section
          if (userProvider.transcriptionVocabulary.isNotEmpty) ...[
            const SizedBox(height: 20),
            Divider(height: 1, color: Colors.grey.shade800),
            const SizedBox(height: 16),
            Wrap(
              spacing: 8,
              runSpacing: 8,
              children: userProvider.transcriptionVocabulary.map((word) {
                final isPendingDelete = _pendingDeletions.contains(word);

                return Container(
                  padding: const EdgeInsets.only(left: 14, right: 6, top: 6, bottom: 6),
                  decoration: BoxDecoration(
                    color: isPendingDelete ? const Color(0xFF1A1A1A) : const Color(0xFF2A2A2E),
                    borderRadius: BorderRadius.circular(100),
                  ),
                  child: Row(
                    mainAxisSize: MainAxisSize.min,
                    children: [
                      Text(
                        word,
                        style: TextStyle(
                          color: isPendingDelete ? Colors.grey.shade600 : Colors.white,
                          fontSize: 14,
                          fontWeight: FontWeight.w500,
                        ),
                      ),
                      const SizedBox(width: 6),
                      if (isPendingDelete)
                        const SizedBox(
                          width: 18,
                          height: 18,
                          child: CircularProgressIndicator(
                            strokeWidth: 2,
                            valueColor: AlwaysStoppedAnimation<Color>(Color(0xFF6B6B6B)),
                          ),
                        )
                      else
                        GestureDetector(
                          onTap: isDisabled ? null : () => _queueWordDeletion(userProvider, word),
                          child: Container(
                            padding: const EdgeInsets.all(4),
                            decoration: BoxDecoration(
                              color: Colors.grey.shade700.withOpacity(0.5),
                              shape: BoxShape.circle,
                            ),
                            child: Icon(
                              Icons.close,
                              color: isDisabled ? Colors.grey.shade700 : Colors.grey.shade300,
                              size: 12,
                            ),
                          ),
                        ),
                    ],
                  ),
                );
              }).toList(),
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

    final success = await userProvider.addVocabularyWords(words);
    if (success && context.mounted) {
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
    MixpanelManager().pageOpened('Custom Vocabulary');

    return GestureDetector(
      onTap: () => FocusScope.of(context).unfocus(),
      child: Scaffold(
        backgroundColor: const Color(0xFF0D0D0D),
        appBar: AppBar(
          backgroundColor: const Color(0xFF0D0D0D),
          elevation: 0,
          leading: IconButton(
            icon: const FaIcon(FontAwesomeIcons.chevronLeft, size: 18),
            onPressed: () => Navigator.of(context).pop(),
          ),
          title: const Text(
            'Custom Vocabulary',
            style: TextStyle(
              color: Colors.white,
              fontSize: 18,
              fontWeight: FontWeight.w600,
            ),
          ),
          centerTitle: true,
        ),
        body: Consumer<UserProvider>(
          builder: (context, userProvider, _) {
            return SingleChildScrollView(
              padding: const EdgeInsets.symmetric(horizontal: 20, vertical: 8),
              child: Column(
                crossAxisAlignment: CrossAxisAlignment.start,
                children: [
                  const SizedBox(height: 16),
                  _buildVocabularyCard(userProvider),
                  const SizedBox(height: 32),
                ],
              ),
            );
          },
        ),
      ),
    );
  }
}
