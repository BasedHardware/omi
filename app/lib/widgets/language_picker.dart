import 'package:flutter/material.dart';
import 'package:omi/providers/locale_provider.dart';
import 'package:omi/utils/l10n_extensions.dart';
import 'package:provider/provider.dart';

class LanguagePickerTile extends StatelessWidget {
  const LanguagePickerTile({super.key});

  @override
  Widget build(BuildContext context) {
    return Consumer<LocaleProvider>(
      builder: (context, localeProvider, child) {
        final currentLocale = localeProvider.locale;
        final displayName = currentLocale != null ? LocaleProvider.getDisplayName(currentLocale) : 'System Default';

        return ListTile(
          title: Text(
            context.l10n.language,
            style: const TextStyle(color: Colors.white),
          ),
          subtitle: Text(
            displayName,
            style: TextStyle(color: Colors.grey.shade400),
          ),
          trailing: const Icon(Icons.chevron_right, color: Colors.grey),
          onTap: () => _showLanguagePicker(context, localeProvider),
        );
      },
    );
  }

  void _showLanguagePicker(BuildContext context, LocaleProvider localeProvider) {
    final supportedLocales = LocaleProvider.supportedLocales;
    final currentLocale = localeProvider.locale;

    showModalBottomSheet(
      context: context,
      backgroundColor: const Color(0xFF1F1F25),
      shape: const RoundedRectangleBorder(
        borderRadius: BorderRadius.vertical(top: Radius.circular(20)),
      ),
      builder: (context) {
        return SafeArea(
          child: Column(
            mainAxisSize: MainAxisSize.min,
            children: [
              Padding(
                padding: const EdgeInsets.all(16),
                child: Text(
                  context.l10n.selectLanguage,
                  style: const TextStyle(
                    color: Colors.white,
                    fontSize: 18,
                    fontWeight: FontWeight.w600,
                  ),
                ),
              ),
              const Divider(height: 1, color: Colors.grey),
              // System Default option
              ListTile(
                leading: Icon(
                  currentLocale == null ? Icons.check_circle : Icons.circle_outlined,
                  color: currentLocale == null ? Colors.green : Colors.grey,
                ),
                title: const Text(
                  'System Default',
                  style: TextStyle(color: Colors.white),
                ),
                onTap: () {
                  localeProvider.setLocale(null);
                  Navigator.pop(context);
                },
              ),
              // Supported locales
              ...supportedLocales.map((locale) {
                final isSelected = currentLocale?.languageCode == locale.languageCode;
                return ListTile(
                  leading: Icon(
                    isSelected ? Icons.check_circle : Icons.circle_outlined,
                    color: isSelected ? Colors.green : Colors.grey,
                  ),
                  title: Text(
                    LocaleProvider.getDisplayName(locale),
                    style: const TextStyle(color: Colors.white),
                  ),
                  onTap: () {
                    localeProvider.setLocale(locale);
                    Navigator.pop(context);
                  },
                );
              }),
              const SizedBox(height: 16),
            ],
          ),
        );
      },
    );
  }
}
