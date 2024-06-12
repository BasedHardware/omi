final Map<String, String> availableLanguages = {
  'Chinese 🇨🇳': 'zh',
  'Dutch 🇳🇱': 'nl',
  'English 🇬🇧': 'en',
  'French 🇫🇷': 'fr',
  'German 🇩🇪': 'de',
  'Greek 🇬🇷': 'el',
  'Hindi 🇮🇳': 'hi',
  'Italian 🇮🇹': 'it',
  'Japanese 🇯🇵': 'ja',
  'Korean 🇰🇷': 'ko',
  'Malay 🇲🇾': 'ms',
  'Norwegian 🇳🇴': 'no',
  'Polish 🇵🇱': 'pl',
  'Portuguese 🇵🇹': 'pt',
  'Russian 🇷🇺': 'ru',
  'Spanish 🇪🇸': 'es',
  'Vietnamese 🇻🇳': 'vi',
};

/// Clean prompt by removing multiple spaces and trimming.
String cleanPrompt(String prompt) {
  return prompt
      .replaceAll(RegExp(r'\s{2,}'), '') // remove sequences of multiple spaces
      .trim();
}

/// Clean LLM response by removing mentiones of `json`, triple backslashes and trimming.
String cleanResponse(String prompt) {
  return prompt
      .replaceAll('```', '')
      .replaceAll('json', '')
      .trim();
}