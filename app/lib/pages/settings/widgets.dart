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
  'Estonian': 'et',
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
  'Romanian': 'ro',
  'Russian': 'ru',
  'Slovak': 'sk',
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
