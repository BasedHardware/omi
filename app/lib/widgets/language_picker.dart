import 'package:flutter/material.dart';

import 'package:provider/provider.dart';

import 'package:omi/providers/locale_provider.dart';
import 'package:omi/utils/l10n_extensions.dart';

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
      backgroundColor: const Color(0xFF1C1C1E),
      shape: const RoundedRectangleBorder(
        borderRadius: BorderRadius.vertical(top: Radius.circular(16)),
      ),
      builder: (context) {
        return SafeArea(
          child: Column(
            mainAxisSize: MainAxisSize.min,
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
              Text(
                context.l10n.selectLanguage,
                style: const TextStyle(
                  color: Colors.white,
                  fontSize: 17,
                  fontWeight: FontWeight.w600,
                ),
              ),
              const SizedBox(height: 16),
              Flexible(
                child: ListView.builder(
                  shrinkWrap: true,
                  physics: const ClampingScrollPhysics(),
                  itemCount: supportedLocales.length,
                  itemBuilder: (context, index) {
                    final locale = supportedLocales[index];
                    final isSelected = currentLocale?.languageCode == locale.languageCode;
                    return ListTile(
                      title: Text(
                        LocaleProvider.getDisplayName(locale),
                        style: TextStyle(
                          color: isSelected ? Colors.white : const Color(0xFF8E8E93),
                          fontWeight: isSelected ? FontWeight.w500 : FontWeight.w400,
                        ),
                      ),
                      trailing: isSelected ? const Icon(Icons.check, color: Colors.white, size: 20) : null,
                      onTap: () {
                        localeProvider.setLocale(locale);
                        Navigator.pop(context);
                      },
                    );
                  },
                ),
              ),
              const SizedBox(height: 16),
            ],
          ),
        );
      },
    );
  }
}
