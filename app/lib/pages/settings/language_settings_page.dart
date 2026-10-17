import 'package:omi/utils/platform/platform_manager.dart';
import 'package:flutter/material.dart';

import 'package:font_awesome_flutter/font_awesome_flutter.dart';
import 'package:provider/provider.dart';

import 'package:omi/pages/settings/transcription/stt_language.dart';
import 'package:omi/providers/capture_provider.dart';
import 'package:omi/providers/home_provider.dart';
import 'package:omi/providers/locale_provider.dart';
import 'package:omi/providers/user_provider.dart';
import 'package:omi/mobile/native_ui/ios_native_surface.dart';
import 'package:omi/ui/ui.dart';
import 'package:omi/utils/l10n_extensions.dart';

class LanguageSettingsPage extends StatefulWidget {
  const LanguageSettingsPage({super.key});

  @override
  State<LanguageSettingsPage> createState() => _LanguageSettingsPageState();
}

class _LanguageSettingsPageState extends State<LanguageSettingsPage> {
  bool _isUpdatingLanguage = false;

  Widget _buildAppInterfaceGroup(LocaleProvider localeProvider) {
    return OmiSettingsGroup(
      header: context.l10n.appInterfaceSectionTitle,
      children: [
        OmiSettingsRow(
          leading: const FaIcon(FontAwesomeIcons.textHeight, size: 16),
          title: context.l10n.appLanguage,
          value: localeProvider.locale != null
              ? LocaleProvider.getDisplayName(localeProvider.locale!)
              : context.l10n.systemDefault,
          onTap: () => _showAppLanguageSelectionSheet(localeProvider),
        ),
      ],
    );
  }

  Widget _buildSpeechTranscriptionGroup(
    HomeProvider homeProvider,
    UserProvider userProvider,
    CaptureProvider captureProvider,
  ) {
    final languageName = homeProvider.userPrimaryLanguage.isNotEmpty
        ? homeProvider.availableLanguages.entries
            .firstWhere(
              (element) => element.value == homeProvider.userPrimaryLanguage,
              orElse: () => MapEntry(context.l10n.notSet, ''),
            )
            .key
        : context.l10n.notSet;

    final isUpdatingTranslation = userProvider.isUpdatingSingleLanguageMode;
    final isAutoTranslationEnabled = !userProvider.singleLanguageMode;
    const translationIcon = FaIcon(FontAwesomeIcons.language, size: 16);

    return OmiSettingsGroup(
      header: context.l10n.speechTranscriptionSectionTitle,
      footer: context.l10n.languageSettingsHelperText,
      children: [
        OmiSettingsRow(
          leading: const FaIcon(FontAwesomeIcons.microphone, size: 16),
          title: context.l10n.primaryLanguage,
          value: languageName,
          trailing: _isUpdatingLanguage ? const OmiSpinner(size: OmiSpinnerSize.small) : null,
          showChevron: !_isUpdatingLanguage,
          onTap: _isUpdatingLanguage ? null : () => _showLanguageSelectionSheet(homeProvider, captureProvider),
        ),
        if (isUpdatingTranslation)
          OmiSettingsRow(
            leading: translationIcon,
            title: context.l10n.automaticTranslation,
            subtitle: context.l10n.detectLanguages,
            trailing: const OmiSpinner(size: OmiSpinnerSize.small),
          )
        else
          OmiSettingsRow.toggle(
            leading: translationIcon,
            title: context.l10n.automaticTranslation,
            subtitle: context.l10n.detectLanguages,
            value: isAutoTranslationEnabled,
            onChanged: (value) async {
              final success = await userProvider.setSingleLanguageMode(!value);
              if (success && mounted) {
                context.read<CaptureProvider>().onTranscriptionSettingsChanged();
              }
            },
          ),
      ],
    );
  }

  void _showAppLanguageSelectionSheet(LocaleProvider localeProvider) {
    final currentLocale = localeProvider.locale;
    showOmiSheet<void>(
      context: context,
      title: context.l10n.appLanguage,
      padding: EdgeInsets.zero,
      builder: (sheetContext) => _LanguageOptionList(
        options: [
          for (final locale in LocaleProvider.supportedLocales)
            (
              label: LocaleProvider.getDisplayName(locale),
              selected: currentLocale?.languageCode == locale.languageCode,
              onTap: () {
                localeProvider.setLocale(locale);
                Navigator.pop(sheetContext);
              },
            ),
        ],
      ),
    );
  }

  void _showLanguageSelectionSheet(HomeProvider homeProvider, CaptureProvider captureProvider) {
    final currentLanguage = homeProvider.userPrimaryLanguage;
    showOmiSheet<void>(
      context: context,
      title: context.l10n.selectLanguage,
      padding: EdgeInsets.zero,
      builder: (sheetContext) => _LanguageOptionList(
        options: [
          for (final entry in homeProvider.availableLanguages.entries)
            (
              label: entry.key,
              selected: entry.value == currentLanguage,
              onTap: () {
                Navigator.pop(sheetContext);
                _setPrimaryLanguage(homeProvider, captureProvider, entry.value);
              },
            ),
        ],
      ),
    );
  }

  Future<void> _setPrimaryLanguage(HomeProvider homeProvider, CaptureProvider captureProvider, String code) async {
    if (_isUpdatingLanguage) return;
    setState(() => _isUpdatingLanguage = true);
    final previous = homeProvider.userPrimaryLanguage;
    try {
      final userProvider = Provider.of<UserProvider>(context, listen: false);
      final success = await homeProvider.updateUserPrimaryLanguage(code, userProvider: userProvider);
      if (success) {
        // Custom STT providers that follow the primary language pick up the new one.
        await SttLanguage.syncToPrimary(code, previous: previous);
        captureProvider.onRecordProfileSettingChanged();
        PlatformManager.instance.analytics.languageChanged(code);
      }
    } finally {
      if (mounted) setState(() => _isUpdatingLanguage = false);
    }
  }

  @override
  Widget build(BuildContext context) {
    PlatformManager.instance.analytics.pageOpened('Language Settings');

    return Consumer4<HomeProvider, UserProvider, CaptureProvider, LocaleProvider>(
      builder: (context, homeProvider, userProvider, captureProvider, localeProvider, _) {
        final classic = Scaffold(
            appBar: AppBar(leading: const OmiBackButton(), title: Text(context.l10n.languageTitle)),
            body: SingleChildScrollView(
              padding: const EdgeInsets.symmetric(horizontal: OmiSpacing.lg, vertical: OmiSpacing.xs),
              child: Column(
                crossAxisAlignment: CrossAxisAlignment.stretch,
                children: [
                  const SizedBox(height: OmiSpacing.md),
                  _buildAppInterfaceGroup(localeProvider),
                  const SizedBox(height: OmiSpacing.xl),
                  _buildSpeechTranscriptionGroup(homeProvider, userProvider, captureProvider),
                  const SizedBox(height: OmiSpacing.xxl),
                ],
              ),
            ));
        final l10n = context.l10n;
        final locales = {
          for (final locale in LocaleProvider.supportedLocales)
            locale.toLanguageTag(): LocaleProvider.getDisplayName(locale)
        };
        return IosNativeSurface(title: l10n.languageTitle, fallback: classic, toolbar: [
          NativeRow('language_back', l10n.back, symbol: 'chevron.left', action: (_) => Navigator.of(context).pop()),
        ], sections: [
          NativeSection(
              'interface',
              [
                NativeRow('app_locale', l10n.appLanguage,
                    kind: 'choice',
                    value: localeProvider.locale?.toLanguageTag() ?? 'system',
                    options: {'system': l10n.systemDefault, ...locales},
                    action: (value) => localeProvider.setLocale(value == 'system'
                        ? null
                        : LocaleProvider.supportedLocales.firstWhere((locale) => locale.toLanguageTag() == value))),
              ],
              title: l10n.appInterfaceSectionTitle),
          NativeSection(
              'speech',
              [
                NativeRow('speech_locale', l10n.primaryLanguage,
                    kind: 'choice',
                    value: homeProvider.userPrimaryLanguage.isEmpty ? 'unset' : homeProvider.userPrimaryLanguage,
                    options: {
                      if (homeProvider.userPrimaryLanguage.isEmpty) 'unset': l10n.notSet,
                      for (final entry in homeProvider.availableLanguages.entries) entry.value: entry.key,
                    },
                    enabled: !_isUpdatingLanguage, action: (value) async {
                  if (value != 'unset') await _setPrimaryLanguage(homeProvider, captureProvider, value as String);
                }),
                NativeRow('automatic_translation', l10n.automaticTranslation,
                    kind: 'toggle',
                    subtitle: l10n.detectLanguages,
                    value: !userProvider.singleLanguageMode,
                    enabled: !userProvider.isUpdatingSingleLanguageMode, action: (value) async {
                  final success = await userProvider.setSingleLanguageMode(!(value as bool));
                  if (success && mounted) captureProvider.onTranscriptionSettingsChanged();
                }),
              ],
              title: l10n.speechTranscriptionSectionTitle,
              footer: l10n.languageSettingsHelperText),
        ]);
      },
    );
  }
}

/// A single-choice list for a language sheet: the selected row is white with a check.
class _LanguageOptionList extends StatelessWidget {
  const _LanguageOptionList({required this.options});

  final List<({String label, bool selected, VoidCallback onTap})> options;

  @override
  Widget build(BuildContext context) {
    return ConstrainedBox(
      constraints: BoxConstraints(maxHeight: MediaQuery.sizeOf(context).height * 0.7),
      child: ListView.builder(
        shrinkWrap: true,
        itemCount: options.length,
        itemBuilder: (context, index) {
          final option = options[index];
          return ListTile(
            selected: option.selected,
            title: Text(
              option.label,
              style: OmiType.body.copyWith(
                color: option.selected ? OmiColors.textPrimary : OmiColors.textSecondary,
                fontWeight: option.selected ? FontWeight.w500 : FontWeight.w400,
              ),
            ),
            trailing: option.selected ? Icon(Icons.check, color: OmiColors.textPrimary, size: 20) : null,
            onTap: option.onTap,
          );
        },
      ),
    );
  }
}
