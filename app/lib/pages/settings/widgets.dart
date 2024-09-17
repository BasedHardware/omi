import 'package:flutter/material.dart';
import 'package:friend_private/backend/preferences.dart';
import 'package:friend_private/utils/analytics/growthbook.dart';
import 'package:friend_private/utils/analytics/mixpanel.dart';

final Map<String, String> availableLanguages = {
  'Bulgarian': 'bg',
  'Catalan': 'ca',
  'Chinese': 'zh',
  'Czech': 'cs',
  'Danish': 'da',
  'Dutch': 'nl',
  'English': 'en',
  'Finnish': 'fi',
  'French': 'fr',
  'German': 'de',
  'Greek': 'el',
  'Hindi': 'hi',
  'Hungarian': 'hu',
  'Indonesian': 'id',
  'Italian': 'it',
  'Japanese': 'ja',
  'Korean': 'ko',
  'Latvian': 'lv',
  'Lithuanian': 'lt',
  'Malay': 'ms',
  'Norwegian': 'no',
  'Polish': 'pl',
  'Portuguese': 'pt',
  'Russian': 'ru',
  'Spanish': 'es',
  'Swedish': 'sv',
  'Thai': 'th',
  'Turkish': 'tr',
  'Ukrainian': 'uk',
  'Vietnamese': 'vi',
};

getLanguageName(String code) {
  return availableLanguages.entries.firstWhere((element) => element.value == code).key;
}

getRecordingSettings(Function(String?) onLanguageChanged, String selectedLanguage) {
  return [
    const Padding(
      padding: EdgeInsets.symmetric(horizontal: 4),
      child: Align(
        alignment: Alignment.centerLeft,
        child: Text(
          'SPEECH LANGUAGE',
          style: TextStyle(color: Colors.white, fontSize: 16, fontWeight: FontWeight.w500),
        ),
      ),
    ),
    const SizedBox(height: 12),
    Center(
        child: Container(
      height: 60,
      decoration: BoxDecoration(
        border: Border.all(color: Colors.white),
        borderRadius: BorderRadius.circular(14),
      ),
      padding: const EdgeInsets.only(left: 16, right: 12, top: 8, bottom: 10),
      child: DropdownButton<String>(
        menuMaxHeight: 350,
        value: selectedLanguage,
        onChanged: onLanguageChanged,
        dropdownColor: Colors.black,
        style: const TextStyle(color: Colors.white, fontSize: 16),
        underline: Container(
          height: 0,
          color: Colors.white,
        ),
        isExpanded: true,
        itemHeight: 48,
        items: availableLanguages.keys.map<DropdownMenuItem<String>>((String key) {
          return DropdownMenuItem<String>(
            value: availableLanguages[key],
            child: Text(
              '$key (${availableLanguages[key]})',
              style: const TextStyle(color: Colors.white, fontWeight: FontWeight.w500, fontSize: 16),
            ),
          );
        }).toList(),
      ),
    )),
    const SizedBox(height: 32.0),
  ];
}

getPreferencesWidgets({
  required VoidCallback onOptInAnalytics,
  required VoidCallback onOptInEmotionalFeedback,
  required VoidCallback viewPrivacyDetails,
  required bool optInAnalytics,
  required bool optInEmotionalFeedback,
  required VoidCallback onDevModeClicked,
  required bool devModeEnabled,
  required VoidCallback onAuthorizeSavingRecordingsClicked,
  required bool authorizeSavingRecordings,
}) {
  return [
    const Align(
      alignment: Alignment.centerLeft,
      child: Text(
        'PREFERENCES',
        style: TextStyle(color: Colors.white, fontSize: 16),
        textAlign: TextAlign.start,
      ),
    ),
    Padding(
      padding: const EdgeInsets.fromLTRB(0, 0, 8, 0),
      child: InkWell(
        onTap: onOptInAnalytics,
        child: Padding(
          padding: const EdgeInsets.symmetric(vertical: 12.0),
          child: Row(
            mainAxisAlignment: MainAxisAlignment.spaceBetween,
            children: [
              Expanded(
                child: GestureDetector(
                  onTap: viewPrivacyDetails,
                  child: const Text(
                    'Help improve Friend by sharing anonymized analytics data',
                    style: TextStyle(
                      color: Color.fromARGB(255, 150, 150, 150),
                      fontSize: 16,
                      decoration: TextDecoration.underline,
                    ),
                  ),
                ),
              ),
              const SizedBox(
                width: 8,
              ),
              Container(
                decoration: BoxDecoration(
                  color: optInAnalytics
                      ? const Color.fromARGB(255, 150, 150, 150)
                      : Colors.transparent, // Fill color when checked
                  border: Border.all(
                    color: const Color.fromARGB(255, 150, 150, 150),
                    width: 2,
                  ),
                  borderRadius: BorderRadius.circular(12),
                ),
                width: 22,
                height: 22,
                child: optInAnalytics // Show the icon only when checked
                    ? const Icon(
                        Icons.check,
                        color: Colors.white, // Tick color
                        size: 18,
                      )
                    : null, // No icon when unchecked
              ),
            ],
          ),
        ),
      ),
    ),
    Padding(
      padding: const EdgeInsets.fromLTRB(0, 0, 8, 0),
      child: InkWell(
        onTap: onAuthorizeSavingRecordingsClicked,
        child: Padding(
          padding: const EdgeInsets.symmetric(vertical: 12.0),
          child: Row(
            mainAxisAlignment: MainAxisAlignment.spaceBetween,
            children: [
              const Text(
                'Authorize saving recordings',
                style: TextStyle(color: Color.fromARGB(255, 150, 150, 150), fontSize: 16),
              ),
              Container(
                decoration: BoxDecoration(
                  color: authorizeSavingRecordings
                      ? const Color.fromARGB(255, 150, 150, 150)
                      : Colors.transparent, // Fill color when checked
                  border: Border.all(
                    color: const Color.fromARGB(255, 150, 150, 150),
                    width: 2,
                  ),
                  borderRadius: BorderRadius.circular(12),
                ),
                width: 22,
                height: 22,
                child: authorizeSavingRecordings // Show the icon only when checked
                    ? const Icon(
                        Icons.check,
                        color: Colors.white, // Tick color
                        size: 18,
                      )
                    : null, // No icon when unchecked
              ),
            ],
          ),
        ),
      ),
    ),
    Visibility(
      visible: GrowthbookUtil().displayOmiFeedback(),
      child: Padding(
        padding: const EdgeInsets.fromLTRB(0, 0, 8, 0),
        child: InkWell(
          onTap:
              (SharedPreferencesUtil().hasSpeakerProfile || optInEmotionalFeedback) ? onOptInEmotionalFeedback : null,
          child: Padding(
            padding: const EdgeInsets.symmetric(vertical: 12.0),
            child: Column(
              mainAxisAlignment: MainAxisAlignment.start,
              crossAxisAlignment: CrossAxisAlignment.start,
              children: [
                Row(
                  mainAxisAlignment: MainAxisAlignment.spaceBetween,
                  children: [
                    const Text(
                      'Enable Omi Feedback',
                      style: TextStyle(
                        color: Color.fromARGB(255, 150, 150, 150),
                        fontSize: 16,
                      ),
                    ),
                    const SizedBox(
                      width: 8,
                    ),
                    Container(
                      decoration: BoxDecoration(
                        color: optInEmotionalFeedback
                            ? const Color.fromARGB(255, 150, 150, 150)
                            : Colors.transparent, // Fill color when checked
                        border: Border.all(
                          color: const Color.fromARGB(255, 150, 150, 150),
                          width: 2,
                        ),
                        borderRadius: BorderRadius.circular(12),
                      ),
                      width: 22,
                      height: 22,
                      child: optInEmotionalFeedback // Show the icon only when checked
                          ? const Icon(
                              Icons.check,
                              color: Colors.white, // Tick color
                              size: 18,
                            )
                          : null, // No icon when unchecked
                    ),
                  ],
                ),
                !SharedPreferencesUtil().hasSpeakerProfile
                    ? const Text(
                        'Set-up your speech profile to enable Omi Feedback',
                        style: TextStyle(
                          fontSize: 14,
                          color: Colors.white,
                        ),
                      )
                    : const SizedBox(),
              ],
            ),
          ),
        ),
      ),
    ),
    // Padding(
    //   padding: const EdgeInsets.fromLTRB(0, 0, 8, 0),
    //   child: InkWell(
    //     onTap: onDevModeClicked,
    //     child: Padding(
    //       padding: const EdgeInsets.symmetric(vertical: 12.0),
    //       child: Row(
    //         mainAxisAlignment: MainAxisAlignment.spaceBetween,
    //         children: [
    //           const Text(
    //             'Enable Developer Mode',
    //             style: TextStyle(color: Color.fromARGB(255, 150, 150, 150), fontSize: 16),
    //           ),
    //           Container(
    //             decoration: BoxDecoration(
    //               color: devModeEnabled
    //                   ? const Color.fromARGB(255, 150, 150, 150)
    //                   : Colors.transparent, // Fill color when checked
    //               border: Border.all(
    //                 color: const Color.fromARGB(255, 150, 150, 150),
    //                 width: 2,
    //               ),
    //               borderRadius: BorderRadius.circular(12),
    //             ),
    //             width: 22,
    //             height: 22,
    //             child: devModeEnabled // Show the icon only when checked
    //                 ? const Icon(
    //                     Icons.check,
    //                     color: Colors.white, // Tick color
    //                     size: 18,
    //                   )
    //                 : null, // No icon when unchecked
    //           ),
    //         ],
    //       ),
    //     ),
    //   ),
    // ),
  ];
}

getItemAddonWrapper(List<Widget> widgets) {
  return Card(
    shape: const RoundedRectangleBorder(borderRadius: BorderRadius.all(Radius.circular(8))),
    child: Column(
      children: widgets,
    ),
  );
}

getItemAddOn(String title, VoidCallback onTap, {required IconData icon, bool visibility = true}) {
  return Visibility(
    visible: visibility,
    child: GestureDetector(
      onTap: onTap,
      child: Padding(
        padding: const EdgeInsets.fromLTRB(0, 12, 8, 0),
        child: Container(
          decoration: BoxDecoration(
            color: const Color.fromARGB(255, 29, 29, 29), // Replace with your desired color
            borderRadius: BorderRadius.circular(10.0), // Adjust for desired rounded corners
          ),
          child: Padding(
            padding: const EdgeInsets.symmetric(horizontal: 16, vertical: 12),
            child: Row(
              mainAxisAlignment: MainAxisAlignment.spaceBetween,
              children: [
                Row(
                  children: [
                    Text(
                      title,
                      style: const TextStyle(color: Color.fromARGB(255, 150, 150, 150), fontSize: 16),
                    ),
                    const SizedBox(width: 16),
                    Icon(icon, color: Colors.white, size: 16),
                  ],
                ),
                const Icon(Icons.arrow_forward_ios, color: Colors.white, size: 16),
              ],
            ),
          ),
        ),
      ),
    ),
  );
}

getItemAddOn2(String title, VoidCallback onTap, {required IconData icon}) {
  return GestureDetector(
    onTap: (){
      MixpanelManager().pageOpened('Settings $title');
      onTap();
    },
    child: Padding(
      padding: const EdgeInsets.fromLTRB(0, 0, 0, 0),
      child: Container(
        decoration: BoxDecoration(
          color: const Color.fromARGB(255, 29, 29, 29),
          borderRadius: BorderRadius.circular(10.0),
        ),
        child: Padding(
          padding: const EdgeInsets.symmetric(horizontal: 16, vertical: 16),
          child: Row(
            mainAxisAlignment: MainAxisAlignment.spaceBetween,
            children: [
              Row(
                children: [
                  Text(
                    title,
                    style: const TextStyle(color: Color.fromARGB(255, 150, 150, 150), fontSize: 16),
                  ),
                  const SizedBox(width: 16),
                  Icon(icon, color: Colors.white, size: 18),
                ],
              ),
              const Icon(Icons.arrow_forward_ios, color: Colors.white, size: 16),
            ],
          ),
        ),
      ),
    ),
  );
}
