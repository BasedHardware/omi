import 'package:flutter/material.dart';

import 'package:provider/provider.dart';

import 'package:omi/pages/settings/transcription/stt_language.dart';
import 'package:omi/providers/capture_provider.dart';
import 'package:omi/providers/home_provider.dart';
import 'package:omi/providers/user_provider.dart';
import 'package:omi/ui/ui.dart';
import 'package:omi/utils/alerts/app_snackbar.dart';
import 'package:omi/utils/l10n_extensions.dart';

/// Asks for the primary language (the one language setting; docs/ux-contract.md §12).
///
/// A searchable list in the shared sheet. When the language is required (none set yet) the sheet
/// cannot be swiped or tapped away and has no close button.
class LanguageSelectionDialog {
  static Future<void> show(
    BuildContext context, {
    bool isRequired = false,
    bool forceShow = false,
    bool showSingleLanguageWarning = false,
  }) async {
    final homeProvider = Provider.of<HomeProvider>(context, listen: false);

    // If the user has already set a primary language and it's not required or forced, don't show the dialog
    if (homeProvider.hasSetPrimaryLanguage && !isRequired && !forceShow) {
      return;
    }

    // If the user's primary language is empty, they haven't set one yet
    if (homeProvider.userPrimaryLanguage.isEmpty) {
      isRequired = true; // Make the dialog required if no language is set
    }

    await showOmiSheet<void>(
      context: context,
      title: context.l10n.tellUsPrimaryLanguage,
      showCloseButton: !isRequired,
      isDismissible: !isRequired,
      enableDrag: !isRequired,
      builder: (sheetContext) => _PrimaryLanguagePicker(
        homeProvider: homeProvider,
        showSingleLanguageWarning: showSingleLanguageWarning,
      ),
    );
  }
}

class _PrimaryLanguagePicker extends StatefulWidget {
  const _PrimaryLanguagePicker({
    required this.homeProvider,
    required this.showSingleLanguageWarning,
  });

  final HomeProvider homeProvider;
  final bool showSingleLanguageWarning;

  @override
  State<_PrimaryLanguagePicker> createState() => _PrimaryLanguagePickerState();
}

class _PrimaryLanguagePickerState extends State<_PrimaryLanguagePicker> {
  // Already ordered by popularity.
  late final List<MapEntry<String, String>> _languages = widget.homeProvider.availableLanguages.entries.toList();
  late List<MapEntry<String, String>> _filtered = _languages;
  final ScrollController _scrollController = ScrollController();

  // Preset the selected language if the user has one
  late String? _selected =
      widget.homeProvider.userPrimaryLanguage.isNotEmpty ? widget.homeProvider.userPrimaryLanguage : null;
  late String? _selectedName = _selected != null ? widget.homeProvider.getLanguageName(_selected!) : null;

  @override
  void initState() {
    super.initState();
    WidgetsBinding.instance.addPostFrameCallback((_) => _scrollToSelected());
  }

  @override
  void dispose() {
    _scrollController.dispose();
    super.dispose();
  }

  void _scrollToSelected() {
    final index = _filtered.indexWhere((lang) => lang.value == _selected);
    if (index == -1 || !_scrollController.hasClients) return;
    _scrollController.animateTo(
      (index * 56.0).clamp(0, _scrollController.position.maxScrollExtent), // Approximate row height
      duration: OmiMotion.of(context).standard,
      curve: Curves.easeInOut,
    );
  }

  void _filter(String query) {
    final q = query.toLowerCase();
    setState(() {
      // A filtered list keeps the original (popularity) order.
      _filtered = q.isEmpty
          ? _languages
          : _languages
              .where((lang) => lang.key.toLowerCase().contains(q) || lang.value.toLowerCase().contains(q))
              .toList();
    });
  }

  Future<void> _save() async {
    final code = _selected;
    if (code == null) return;
    final successMsg = context.l10n.languageSetTo(_selectedName ?? code);
    final failMsg = context.l10n.failedToSetLanguage;
    final userProvider = Provider.of<UserProvider>(context, listen: false);
    final previous = widget.homeProvider.userPrimaryLanguage;
    final success = await widget.homeProvider.updateUserPrimaryLanguage(code, userProvider: userProvider);
    if (!mounted) return;
    if (success) {
      // Custom STT providers that follow the primary language pick up the new one.
      await SttLanguage.syncToPrimary(code, previous: previous);
      if (!mounted) return;
      Provider.of<CaptureProvider>(context, listen: false).onRecordProfileSettingChanged();
      Navigator.of(context).pop();
      AppSnackbar.showSnackbarSuccess(successMsg);
    } else {
      AppSnackbar.showSnackbarError(failMsg);
    }
  }

  @override
  Widget build(BuildContext context) {
    final l10n = context.l10n;
    return Column(
      mainAxisSize: MainAxisSize.min,
      crossAxisAlignment: CrossAxisAlignment.stretch,
      children: [
        Text(l10n.languageForTranscription, style: OmiType.subhead.copyWith(color: OmiColors.textSecondary)),
        if (widget.showSingleLanguageWarning) ...[
          const SizedBox(height: OmiSpacing.xs),
          Container(
            padding: const EdgeInsets.all(OmiSpacing.sm),
            decoration: BoxDecoration(
              color: OmiColors.surface2,
              borderRadius: OmiRadius.smAll,
              border: Border.all(color: OmiColors.border),
            ),
            child: Row(
              children: [
                const Icon(Icons.info_outline, color: OmiColors.textTertiary, size: 18),
                const SizedBox(width: OmiSpacing.xs),
                Expanded(
                  child: Text(
                    l10n.singleLanguageModeInfo,
                    style: OmiType.footnote.copyWith(color: OmiColors.textSecondary),
                  ),
                ),
              ],
            ),
          ),
        ],
        const SizedBox(height: OmiSpacing.sm),
        OmiSearchField(placeholder: l10n.searchLanguageHint, onChanged: _filter, onCleared: () => _filter('')),
        const SizedBox(height: OmiSpacing.xs),
        SizedBox(
          height: MediaQuery.sizeOf(context).height * 0.4,
          child: _filtered.isEmpty
              ? Center(
                  child: Text(l10n.noLanguagesFound, style: OmiType.subhead.copyWith(color: OmiColors.textTertiary)),
                )
              : ListView.builder(
                  controller: _scrollController,
                  itemCount: _filtered.length,
                  itemBuilder: (context, index) {
                    final language = _filtered[index];
                    final isSelected = _selected == language.value;
                    return ListTile(
                      title: Text(language.key, style: OmiType.body),
                      trailing: isSelected ? const Icon(Icons.check_circle, color: OmiColors.textPrimary) : null,
                      selected: isSelected,
                      selectedTileColor: OmiColors.surface2,
                      shape: const RoundedRectangleBorder(borderRadius: OmiRadius.smAll),
                      onTap: () => setState(() {
                        // Tapping the selected language clears the choice.
                        if (isSelected) {
                          _selected = null;
                          _selectedName = null;
                        } else {
                          _selected = language.value;
                          _selectedName = language.key;
                        }
                      }),
                    );
                  },
                ),
        ),
        const SizedBox(height: OmiSpacing.sm),
        OmiButton(label: l10n.save, expand: true, onPressed: _selected == null ? null : _save),
        const SizedBox(height: OmiSpacing.xs),
      ],
    );
  }
}
