import 'dart:async';

import 'package:omi/utils/platform/platform_manager.dart';
import 'package:flutter/material.dart';

import 'package:font_awesome_flutter/font_awesome_flutter.dart';
import 'package:provider/provider.dart';

import 'package:omi/providers/capture_provider.dart';
import 'package:omi/mobile/native_ui/ios_native_surface.dart';
import 'package:omi/providers/user_provider.dart';
import 'package:omi/ui/ui.dart';
import 'package:omi/utils/l10n_extensions.dart';

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
    final l10n = context.l10n;
    final isDisabled = _isDeletingBatch || userProvider.isUpdatingVocabulary;
    final isAdding = userProvider.isUpdatingVocabulary && !_isDeletingBatch;
    final words = userProvider.transcriptionVocabulary;

    return Container(
      padding: const EdgeInsets.all(OmiSpacing.md),
      decoration: BoxDecoration(color: OmiColors.surface1, borderRadius: OmiRadius.lgAll),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          // Header row with icon
          Row(
            children: [
              Container(
                width: 40,
                height: 40,
                decoration: BoxDecoration(color: OmiColors.surface2, borderRadius: OmiRadius.mdAll),
                child: Center(child: FaIcon(FontAwesomeIcons.book, color: OmiColors.textSecondary, size: 16)),
              ),
              const SizedBox(width: 14),
              Expanded(
                child: Column(
                  crossAxisAlignment: CrossAxisAlignment.start,
                  children: [
                    Row(
                      children: [
                        Flexible(
                          child: Text(l10n.addWords, style: OmiType.callout.copyWith(fontWeight: FontWeight.w500)),
                        ),
                        const SizedBox(width: OmiSpacing.xs),
                        Semantics(
                          label: l10n.vocabularyWordCount(words.length),
                          excludeSemantics: true,
                          child: Container(
                            padding: const EdgeInsets.symmetric(horizontal: OmiSpacing.xs, vertical: OmiSpacing.xxs),
                            decoration: BoxDecoration(color: OmiColors.surface3, borderRadius: OmiRadius.smAll),
                            child: Text(
                              '${words.length}',
                              style: OmiType.caption.copyWith(
                                color: OmiColors.textSecondary,
                                fontWeight: FontWeight.w500,
                              ),
                            ),
                          ),
                        ),
                      ],
                    ),
                    const SizedBox(height: 2),
                    Text(l10n.addWordsDesc, style: OmiType.footnote.copyWith(color: OmiColors.textTertiary)),
                  ],
                ),
              ),
            ],
          ),
          const SizedBox(height: OmiSpacing.lg),

          // Input field
          Row(
            children: [
              Expanded(
                child: TextField(
                  controller: _vocabularyController,
                  enabled: !isAdding,
                  style: OmiType.subhead,
                  decoration: InputDecoration(
                    hintText: l10n.vocabularyHint,
                    hintStyle: OmiType.subhead.copyWith(color: OmiColors.textTertiary),
                    filled: true,
                    fillColor: OmiColors.surface2,
                    contentPadding: const EdgeInsets.symmetric(horizontal: OmiSpacing.md, vertical: 14),
                    border: const OutlineInputBorder(borderRadius: OmiRadius.mdAll, borderSide: BorderSide.none),
                    enabledBorder: const OutlineInputBorder(borderRadius: OmiRadius.mdAll, borderSide: BorderSide.none),
                    focusedBorder: OutlineInputBorder(
                      borderRadius: OmiRadius.mdAll,
                      borderSide: BorderSide(color: OmiColors.border),
                    ),
                  ),
                  onSubmitted: isAdding ? null : (value) => _addWord(userProvider),
                ),
              ),
              const SizedBox(width: OmiSpacing.xs),
              if (isAdding)
                const SizedBox(
                  width: kOmiMinTapTarget,
                  height: kOmiMinTapTarget,
                  child: Center(child: OmiSpinner(size: OmiSpinnerSize.small)),
                )
              else
                OmiIconButton.filled(
                  icon: const FaIcon(FontAwesomeIcons.plus, size: 16),
                  label: l10n.add,
                  fillColor: OmiColors.surface2,
                  diameter: kOmiMinTapTarget,
                  onPressed: userProvider.isUpdatingVocabulary ? null : () => _addWord(userProvider),
                ),
            ],
          ),

          // Words chips section
          if (words.isNotEmpty) ...[
            const SizedBox(height: OmiSpacing.lg),
            Divider(height: 1, color: OmiColors.border),
            const SizedBox(height: OmiSpacing.md),
            Wrap(
              spacing: OmiSpacing.xs,
              runSpacing: OmiSpacing.xs,
              children: words.map((word) {
                final isPendingDelete = _pendingDeletions.contains(word);

                return Container(
                  padding: const EdgeInsets.only(left: 14),
                  decoration: BoxDecoration(
                    color: isPendingDelete ? OmiColors.surface1 : OmiColors.surface2,
                    borderRadius: OmiRadius.pillAll,
                  ),
                  child: Row(
                    mainAxisSize: MainAxisSize.min,
                    children: [
                      Text(
                        word,
                        style: OmiType.subhead.copyWith(
                          color: isPendingDelete ? OmiColors.textTertiary : OmiColors.textPrimary,
                          fontWeight: FontWeight.w500,
                        ),
                      ),
                      if (isPendingDelete)
                        SizedBox(
                          width: kOmiMinTapTarget,
                          height: kOmiMinTapTarget,
                          child: Center(child: OmiSpinner(size: OmiSpinnerSize.small, color: OmiColors.textTertiary)),
                        )
                      else
                        OmiIconButton.filled(
                          icon: const Icon(Icons.close, size: 12),
                          label: l10n.removeVocabularyWord(word),
                          color: OmiColors.textSecondary,
                          fillColor: OmiColors.surface3,
                          diameter: 20,
                          onPressed: isDisabled ? null : () => _queueWordDeletion(userProvider, word),
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
    if (success && mounted) {
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
    PlatformManager.instance.analytics.pageOpened('Custom Vocabulary');

    final classic = GestureDetector(
      onTap: () => FocusScope.of(context).unfocus(),
      child: Scaffold(
        appBar: AppBar(leading: const OmiBackButton(), title: Text(context.l10n.customVocabularyTitle)),
        body: Consumer<UserProvider>(
          builder: (context, userProvider, _) {
            return SingleChildScrollView(
              padding: const EdgeInsets.symmetric(horizontal: OmiSpacing.lg, vertical: OmiSpacing.xs),
              child: Column(
                crossAxisAlignment: CrossAxisAlignment.start,
                children: [
                  const SizedBox(height: OmiSpacing.md),
                  _buildVocabularyCard(userProvider),
                  const SizedBox(height: OmiSpacing.xxl),
                ],
              ),
            );
          },
        ),
      ),
    );
    final userProvider = context.watch<UserProvider>();
    final l10n = context.l10n;
    final disabled = _isDeletingBatch || userProvider.isUpdatingVocabulary;
    return IosNativeSurface(title: l10n.customVocabularyTitle, fallback: classic, toolbar: [
      NativeRow('vocabulary_back', l10n.back, symbol: 'chevron.left', action: (_) => Navigator.of(context).maybePop())
    ], sections: [
      NativeSection(
          'vocabulary_entry',
          [
            NativeRow('vocabulary_draft', l10n.vocabularyHint,
                kind: 'text',
                value: _vocabularyController.text,
                enabled: !userProvider.isUpdatingVocabulary,
                action: (value) => setState(() => _vocabularyController.text = value as String)),
            NativeRow('vocabulary_add', l10n.add,
                symbol: 'plus', enabled: !userProvider.isUpdatingVocabulary, action: (_) => _addWord(userProvider)),
          ],
          title: l10n.addWords,
          footer: l10n.addWordsDesc),
      NativeSection(
          'vocabulary_words',
          [
            for (final word in userProvider.transcriptionVocabulary)
              NativeRow('vocabulary_word_$word', word,
                  subtitle: l10n.removeVocabularyWord(word),
                  symbol: 'minus.circle',
                  destructive: true,
                  enabled: !disabled && !_pendingDeletions.contains(word),
                  action: (_) => _queueWordDeletion(userProvider, word)),
          ],
          title: l10n.vocabularyWordCount(userProvider.transcriptionVocabulary.length)),
    ]);
  }
}
