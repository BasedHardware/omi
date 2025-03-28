import 'package:flutter/material.dart';
import 'package:omi/backend/preferences.dart';
import 'package:omi/utils/analytics/mixpanel.dart';
import 'package:omi/widgets/dialog.dart';

class SpeechLanguageSheet extends StatelessWidget {
  final String recordingLanguage;
  final Function(String) setRecordingLanguage;
  final Map<String, String> availableLanguages;
  final List<String> autoDetectionSupportedLanguages;

  const SpeechLanguageSheet({
    super.key,
    required this.recordingLanguage,
    required this.setRecordingLanguage,
    required this.availableLanguages,
    required this.autoDetectionSupportedLanguages,
  });

  @override
  Widget build(BuildContext context) {
    return GestureDetector(
      onTap: () {
        showModalBottomSheet(
          context: context,
          isScrollControlled: true,
          backgroundColor: Colors.transparent,
          builder: (ctx) {
            return Container(
              decoration: const BoxDecoration(
                color: Colors.black,
                borderRadius: BorderRadius.only(
                  topLeft: Radius.circular(16),
                  topRight: Radius.circular(16),
                ),
              ),
              constraints: BoxConstraints(
                maxHeight: MediaQuery.of(context).size.height * 0.75,
              ),
              child: Column(
                mainAxisSize: MainAxisSize.min,
                children: [
                  const SizedBox(height: 8),
                  Container(
                    height: 5,
                    width: 40,
                    decoration: BoxDecoration(
                      color: Colors.grey.shade600,
                      borderRadius: BorderRadius.circular(3),
                    ),
                  ),
                  const SizedBox(height: 14),
                  Row(
                    children: [
                      const Padding(
                        padding: EdgeInsets.symmetric(horizontal: 16),
                        child: Text(
                          'SPEECH LANGUAGE',
                          style: TextStyle(color: Colors.white, fontSize: 16, fontWeight: FontWeight.w500),
                        ),
                      ),
                      const Spacer(),
                      IconButton(
                        onPressed: () {
                          Navigator.of(context).pop();
                        },
                        icon: const Icon(Icons.close, color: Colors.white),
                      ),
                    ],
                  ),
                  Divider(
                    color: Colors.grey.shade600,
                    endIndent: 6,
                    indent: 6,
                    thickness: 0.8,
                  ),
                  Expanded(
                    child: ListView.builder(
                      shrinkWrap: true,
                      itemCount: availableLanguages.length,
                      itemBuilder: (ctx, i) {
                        final languageName = availableLanguages.keys.toList()[i];
                        final languageCode = availableLanguages.values.toList()[i];
                        final isSelected = languageCode == recordingLanguage;

                        // Custom layout for the Auto Detection option
                        if (languageName == 'Auto Detection') {
                          return Column(
                            crossAxisAlignment: CrossAxisAlignment.start,
                            children: [
                              ListTile(
                                title: Text(
                                  '$languageName ($languageCode)',
                                  style: TextStyle(
                                    color: isSelected ? Colors.white : Color(0xDDFFFFFF),
                                    fontWeight: isSelected ? FontWeight.w600 : FontWeight.normal,
                                  ),
                                ),
                                trailing: isSelected ? const Icon(Icons.check, size: 20, color: Colors.white) : null,
                                subtitle: Text(
                                  'Supports 10 languages (beta)',
                                  style: TextStyle(
                                    color: Colors.white.withOpacity(0.5),
                                    fontSize: 12,
                                  ),
                                ),
                                tileColor: isSelected ? Colors.white.withOpacity(0.15) : null,
                                shape: RoundedRectangleBorder(
                                  borderRadius: BorderRadius.circular(8),
                                ),
                                contentPadding: const EdgeInsets.symmetric(horizontal: 16, vertical: 4),
                                onTap: () => _handleLanguageSelection(context, languageCode),
                              ),
                              Padding(
                                padding: const EdgeInsets.only(left: 16, right: 16, bottom: 12),
                                child: Wrap(
                                  spacing: 6,
                                  runSpacing: 6,
                                  children: autoDetectionSupportedLanguages.map((language) {
                                    return Container(
                                      padding: const EdgeInsets.symmetric(horizontal: 8, vertical: 4),
                                      decoration: BoxDecoration(
                                        color: isSelected ? Colors.white.withOpacity(0.15) : Colors.transparent,
                                        borderRadius: BorderRadius.circular(12),
                                        border: Border.all(
                                          color: Colors.white.withOpacity(0.3),
                                          width: 0.5,
                                        ),
                                      ),
                                      child: Text(
                                        language,
                                        style: TextStyle(
                                          color: isSelected ? Colors.white : Colors.white.withOpacity(0.7),
                                          fontSize: 11,
                                        ),
                                      ),
                                    );
                                  }).toList(),
                                ),
                              ),
                              Divider(color: Colors.grey.shade800, thickness: 1.0),
                            ],
                          );
                        }

                        // Standard layout for other language options
                        return ListTile(
                          title: Text(
                            '$languageName ($languageCode)',
                            style: TextStyle(
                              color: isSelected ? Colors.white : Color(0xDDFFFFFF),
                              fontWeight: isSelected ? FontWeight.w600 : FontWeight.normal,
                            ),
                          ),
                          tileColor: isSelected ? Colors.white.withOpacity(0.15) : null,
                          shape: RoundedRectangleBorder(
                            borderRadius: BorderRadius.circular(8),
                          ),
                          contentPadding: const EdgeInsets.symmetric(horizontal: 16, vertical: 4),
                          trailing: isSelected ? const Icon(Icons.check, size: 20, color: Colors.white) : null,
                          onTap: () => _handleLanguageSelection(context, languageCode),
                        );
                      },
                    ),
                  ),
                ],
              ),
            );
          },
        );
      },
      child: Container(
        decoration: BoxDecoration(
          borderRadius: BorderRadius.circular(10),
        ),
        padding: const EdgeInsets.symmetric(horizontal: 14, vertical: 4),
        child: Row(
          crossAxisAlignment: CrossAxisAlignment.center,
          children: [
            const Icon(
              Icons.language,
              color: Colors.white,
              size: 24,
            ),
            const SizedBox(width: 4),
            Text(
              SharedPreferencesUtil().recordingsLanguage.toUpperCase(),
              style: const TextStyle(color: Colors.white, fontSize: 14, fontWeight: FontWeight.bold),
            ),
          ],
        ),
      ),
    );
  }

  void _handleLanguageSelection(BuildContext context, String newValue) {
    if (newValue == recordingLanguage) return;

    if (newValue == 'auto') {
      showDialog(
        context: context,
        barrierDismissible: false,
        builder: (c) => getDialog(
          context,
          () => Navigator.of(context).pop(),
          () => {},
          'Language Limitations',
          'Auto language detection is currently supported for 10 languages and is still in beta. Quality is not guaranteed.',
          singleButton: true,
        ),
      ).whenComplete(() => Navigator.of(context).pop());
    }
    if (newValue != 'en' && newValue != 'auto') {
      showDialog(
        context: context,
        barrierDismissible: false,
        builder: (c) => getDialog(
          context,
          () => Navigator.of(context).pop(),
          () => {},
          'Language Limitations',
          'Speech profiles are only available for English language. We are working on adding support for other languages.',
          singleButton: true,
        ),
      ).whenComplete(() => Navigator.of(context).pop());
    }

    setRecordingLanguage(newValue);
    MixpanelManager().recordingLanguageChanged(newValue);

    if (Navigator.of(context).canPop() && newValue == 'en') {
      Navigator.of(context).pop();
    }
  }
}
