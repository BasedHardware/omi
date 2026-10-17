import 'package:flutter/material.dart';

import 'package:provider/provider.dart';

import 'package:omi/mobile/native_ui/ios_native_surface.dart';
import 'package:omi/pages/settings/transcription/stt_language.dart';
import 'package:omi/providers/capture_provider.dart';
import 'package:omi/providers/home_provider.dart';
import 'package:omi/providers/user_provider.dart';
import 'package:omi/ui/ui.dart';
import 'package:omi/utils/alerts/app_snackbar.dart';
import 'package:omi/utils/l10n_extensions.dart';

/// Asks for the primary language (the one language setting; docs/ux-contract.md §12).
///
/// A searchable list in the shared sheet. It always closes (X, swipe, scrim tap): a user with no
/// saved language keeps the default and is asked again next session, never held on a sheet whose
/// save may not succeed (a backend fence, no network).
class LanguageSelectionDialog {
  static Future<void> show(
    BuildContext context, {
    bool forceShow = false,
    bool showSingleLanguageWarning = false,
  }) async {
    final homeProvider = Provider.of<HomeProvider>(context, listen: false);

    // A language is already set; only an explicit request reopens the picker.
    if (homeProvider.hasSetPrimaryLanguage && !forceShow) {
      return;
    }

    await showOmiSheet<void>(
      context: context,
      title: context.l10n.tellUsPrimaryLanguage,
      builder: (sheetContext) => _PrimaryLanguagePicker(
        homeProvider: homeProvider,
        showSingleLanguageWarning: showSingleLanguageWarning,
      ),
      nativeBuilder: (sheetContext) => NativePrimaryLanguagePicker(
        homeProvider: homeProvider,
        showSingleLanguageWarning: showSingleLanguageWarning,
      ),
    );
  }
}

/// Saves [code] through the existing owners: the primary language, the custom STT providers that
/// follow it and the capture profile. On success it closes the sheet ([context]) and confirms; on
/// failure the sheet stays and reports it.
Future<void> _savePrimaryLanguage(BuildContext context, HomeProvider homeProvider, String code, String? name) async {
  final successMsg = context.l10n.languageSetTo(name ?? code);
  final failMsg = context.l10n.failedToSetLanguage;
  final userProvider = Provider.of<UserProvider>(context, listen: false);
  final previous = homeProvider.userPrimaryLanguage;
  final success = await homeProvider.updateUserPrimaryLanguage(code, userProvider: userProvider);
  if (!context.mounted) return;
  if (success) {
    // Custom STT providers that follow the primary language pick up the new one.
    await SttLanguage.syncToPrimary(code, previous: previous);
    if (!context.mounted) return;
    Provider.of<CaptureProvider>(context, listen: false).onRecordProfileSettingChanged();
    Navigator.of(context).pop();
    AppSnackbar.showSnackbarSuccess(successMsg);
  } else {
    AppSnackbar.showSnackbarError(failMsg);
  }
}

/// The primary-language sheet as one native surface: the same description, single-language note,
/// search and languages (in popularity order, the choice checked; tapping it again clears it),
/// with Close and Save in the toolbar. Save applies once through [_savePrimaryLanguage]. A host
/// that cannot draw it keeps the complete Flutter sheet.
class NativePrimaryLanguagePicker extends StatefulWidget {
  const NativePrimaryLanguagePicker({super.key, required this.homeProvider, required this.showSingleLanguageWarning});

  final HomeProvider homeProvider;
  final bool showSingleLanguageWarning;

  @override
  State<NativePrimaryLanguagePicker> createState() => _NativePrimaryLanguagePickerState();
}

class _NativePrimaryLanguagePickerState extends State<NativePrimaryLanguagePicker> {
  late final List<MapEntry<String, String>> _languages = widget.homeProvider.availableLanguages.entries.toList();
  late String? _selected =
      widget.homeProvider.userPrimaryLanguage.isNotEmpty ? widget.homeProvider.userPrimaryLanguage : null;
  late String? _selectedName = _selected != null ? widget.homeProvider.getLanguageName(_selected!) : null;
  String _query = '';
  bool _saving = false;

  Future<void> _save() async {
    final code = _selected;
    // A sheet that is already closing (a save succeeded) never saves or pops again.
    if (code == null || _saving || ModalRoute.of(context)?.isCurrent == false) return;
    setState(() => _saving = true);
    try {
      await _savePrimaryLanguage(context, widget.homeProvider, code, _selectedName);
    } finally {
      if (mounted) setState(() => _saving = false);
    }
  }

  void _toggle(MapEntry<String, String> language) => setState(() {
        // Tapping the selected language clears the choice.
        if (_selected == language.value) {
          _selected = null;
          _selectedName = null;
        } else {
          _selected = language.value;
          _selectedName = language.key;
        }
      });

  @override
  Widget build(BuildContext context) {
    final l10n = context.l10n;
    final q = _query.toLowerCase();
    final filtered = [
      for (final (index, language) in _languages.indexed)
        if (q.isEmpty || language.key.toLowerCase().contains(q) || language.value.toLowerCase().contains(q))
          (index, language),
    ];
    return IosNativeSurface(
      title: l10n.tellUsPrimaryLanguage,
      fallback: OmiSheetScaffold(
        title: l10n.tellUsPrimaryLanguage,
        child: _PrimaryLanguagePicker(
          homeProvider: widget.homeProvider,
          showSingleLanguageWarning: widget.showSingleLanguageWarning,
        ),
      ),
      search: (value) => setState(() => _query = value as String),
      searchValue: _query,
      searchPlaceholder: l10n.searchLanguageHint,
      toolbar: [
        NativeRow('language_close', l10n.close, symbol: 'xmark', action: (_) {
          if (ModalRoute.of(context)?.isCurrent == false) return;
          Navigator.of(context).maybePop();
        }),
        NativeRow('language_save', l10n.save, enabled: _selected != null && !_saving, action: (_) => _save()),
      ],
      sections: [
        NativeSection('language_intro', [
          NativeRow('language_description', l10n.languageForTranscription, kind: 'label'),
          if (widget.showSingleLanguageWarning)
            NativeRow('language_single_mode', l10n.singleLanguageModeInfo, kind: 'label', symbol: 'info.circle'),
        ]),
        NativeSection('language_options', [
          if (filtered.isEmpty) NativeRow('language_none', l10n.noLanguagesFound, kind: 'label'),
          for (final (index, language) in filtered)
            NativeRow('language_$index', language.key,
                symbol: _selected == language.value ? 'checkmark' : null, action: (_) => _toggle(language)),
        ]),
      ],
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
    await _savePrimaryLanguage(context, widget.homeProvider, code, _selectedName);
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
                Icon(Icons.info_outline, color: OmiColors.textTertiary, size: 18),
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
                      trailing: isSelected ? Icon(Icons.check_circle, color: OmiColors.textPrimary) : null,
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
