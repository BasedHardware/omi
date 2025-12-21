import 'package:flutter/material.dart';
import 'package:font_awesome_flutter/font_awesome_flutter.dart';
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
  bool _isUpdatingLanguage = false;

  Widget _buildLanguageCard(
    HomeProvider homeProvider,
    UserProvider userProvider,
    CaptureProvider captureProvider,
  ) {
    final languageName = homeProvider.userPrimaryLanguage.isNotEmpty
        ? homeProvider.availableLanguages.entries
            .firstWhere(
              (element) => element.value == homeProvider.userPrimaryLanguage,
              orElse: () => const MapEntry('Not set', ''),
            )
            .key
        : 'Not set';

    final isUpdatingTranslation = userProvider.isUpdatingSingleLanguageMode;
    final isAutoTranslationEnabled = !userProvider.singleLanguageMode;

    return Container(
      padding: const EdgeInsets.all(16),
      decoration: BoxDecoration(
        color: const Color(0xFF1C1C1E),
        borderRadius: BorderRadius.circular(14),
      ),
      child: Column(
        children: [
          // Primary Language Row
          GestureDetector(
            onTap: _isUpdatingLanguage ? null : () => _showLanguageSelectionSheet(homeProvider, captureProvider),
            child: Row(
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
                      FontAwesomeIcons.globe,
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
                      const Text(
                        'Primary Language',
                        style: TextStyle(
                          color: Colors.white,
                          fontSize: 16,
                          fontWeight: FontWeight.w500,
                        ),
                      ),
                      const SizedBox(height: 2),
                      Text(
                        languageName,
                        style: TextStyle(
                          color: Colors.grey.shade500,
                          fontSize: 13,
                        ),
                      ),
                    ],
                  ),
                ),
                if (_isUpdatingLanguage)
                  const SizedBox(
                    width: 20,
                    height: 20,
                    child: CircularProgressIndicator(
                      strokeWidth: 2,
                      valueColor: AlwaysStoppedAnimation<Color>(Colors.white),
                    ),
                  )
                else
                  FaIcon(
                    FontAwesomeIcons.chevronRight,
                    color: Colors.grey.shade600,
                    size: 14,
                  ),
              ],
            ),
          ),

          Padding(
            padding: const EdgeInsets.symmetric(vertical: 16),
            child: Divider(height: 1, color: Colors.grey.shade800),
          ),

          // Automatic Translation Row
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
                    FontAwesomeIcons.language,
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
                    const Text(
                      'Automatic Translation',
                      style: TextStyle(
                        color: Colors.white,
                        fontSize: 16,
                        fontWeight: FontWeight.w500,
                      ),
                    ),
                    const SizedBox(height: 2),
                    Text(
                      'Detect 10+ languages',
                      style: TextStyle(
                        color: Colors.grey.shade500,
                        fontSize: 13,
                      ),
                    ),
                  ],
                ),
              ),
              const SizedBox(width: 12),
              if (isUpdatingTranslation)
                const SizedBox(
                  width: 24,
                  height: 24,
                  child: CircularProgressIndicator(
                    strokeWidth: 2,
                    valueColor: AlwaysStoppedAnimation<Color>(Colors.white),
                  ),
                )
              else
                Switch(
                  value: isAutoTranslationEnabled,
                  onChanged: (value) async {
                    final success = await userProvider.setSingleLanguageMode(!value);
                    if (success && context.mounted) {
                      context.read<CaptureProvider>().onTranscriptionSettingsChanged();
                    }
                  },
                  activeColor: const Color(0xFF22C55E),
                ),
            ],
          ),
        ],
      ),
    );
  }

  void _showLanguageSelectionSheet(HomeProvider homeProvider, CaptureProvider captureProvider) {
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
                                      final success = await homeProvider.updateUserPrimaryLanguage(entry.value);
                                      if (success) {
                                        captureProvider.onRecordProfileSettingChanged();
                                      }
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

  @override
  Widget build(BuildContext context) {
    MixpanelManager().pageOpened('Language Settings');

    return Scaffold(
      backgroundColor: const Color(0xFF0D0D0D),
      appBar: AppBar(
        backgroundColor: const Color(0xFF0D0D0D),
        elevation: 0,
        leading: IconButton(
          icon: const FaIcon(FontAwesomeIcons.chevronLeft, size: 18),
          onPressed: () => Navigator.of(context).pop(),
        ),
        title: const Text(
          'Language',
          style: TextStyle(
            color: Colors.white,
            fontSize: 18,
            fontWeight: FontWeight.w600,
          ),
        ),
        centerTitle: true,
      ),
      body: Consumer3<HomeProvider, UserProvider, CaptureProvider>(
        builder: (context, homeProvider, userProvider, captureProvider, _) {
          return SingleChildScrollView(
            padding: const EdgeInsets.symmetric(horizontal: 20, vertical: 8),
            child: Column(
              crossAxisAlignment: CrossAxisAlignment.start,
              children: [
                const SizedBox(height: 16),
                _buildLanguageCard(homeProvider, userProvider, captureProvider),
                const SizedBox(height: 32),
              ],
            ),
          );
        },
      ),
    );
  }
}
