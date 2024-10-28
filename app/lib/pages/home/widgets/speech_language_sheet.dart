import 'package:flutter/material.dart';
import 'package:friend_private/backend/preferences.dart';
import 'package:friend_private/utils/analytics/mixpanel.dart';
import 'package:friend_private/widgets/dialog.dart';

class SpeechLanguageSheet extends StatelessWidget {
  final String recordingLanguage;
  final Function(String) setRecordingLanguage;
  final Map<String, String> availableLanguages;

  const SpeechLanguageSheet({
    super.key,
    required this.recordingLanguage,
    required this.setRecordingLanguage,
    required this.availableLanguages,
  });

  @override
  Widget build(BuildContext context) {
    return GestureDetector(
      onTap: () {
        showModalBottomSheet(
          context: context,
          builder: (ctx) {
            return Container(
              color: Colors.black,
              child: Column(
                mainAxisSize: MainAxisSize.min,
                children: [
                  const SizedBox(height: 14),
                  Row(
                    children: [
                      const Padding(
                        padding: EdgeInsets.symmetric(horizontal: 12),
                        child: Align(
                          alignment: Alignment.centerLeft,
                          child: Text(
                            'SPEECH LANGUAGE',
                            style: TextStyle(color: Colors.white, fontSize: 16, fontWeight: FontWeight.w500),
                          ),
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
                        return ListTile(
                          title: Text(
                            '${availableLanguages.keys.toList()[i]} (${availableLanguages.values.toList()[i]})',
                            style: const TextStyle(color: Colors.white),
                          ),
                          onTap: () {
                            var newValue = availableLanguages.values.toList()[i];
                            if (newValue == recordingLanguage) return;
                            if (newValue != 'en') {
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
                          },
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
        width: MediaQuery.of(context).size.width * 0.19,
        height: MediaQuery.of(context).size.height * 0.041,
        decoration: BoxDecoration(
          border: Border.all(
            color: Colors.grey,
            width: 1,
          ),
          borderRadius: BorderRadius.circular(10),
        ),
        padding: const EdgeInsets.only(left: 12, right: 4),
        child: Row(
          children: [
            const Spacer(
              flex: 1,
            ),
            Text(
              SharedPreferencesUtil().recordingsLanguage,
              style: const TextStyle(color: Colors.white, fontWeight: FontWeight.w500, fontSize: 16),
              textAlign: TextAlign.center,
            ),
            const Spacer(
              flex: 2,
            ),
            const Icon(Icons.arrow_drop_down, color: Colors.white),
          ],
        ),
      ),
    );
  }
}
