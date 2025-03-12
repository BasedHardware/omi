// A script to extract Firebase configuration from hardcoded files and generate environment variable entries
// Usage: dart run scripts/firebase_config_to_env.dart [dev|prod]

import 'dart:io';

void main(List<String> args) async {
  if (args.isEmpty || (args[0] != 'dev' && args[0] != 'prod')) {
    print('Usage: dart run scripts/firebase_config_to_env.dart [dev|prod]');
    exit(1);
  }

  final environment = args[0];
  final filePath = 'lib/firebase_options_${environment}.dart';

  if (!await File(filePath).exists()) {
    print('Error: File $filePath does not exist');
    exit(1);
  }

  final fileContent = await File(filePath).readAsString();

  // Extract Android configuration
  final androidApiKey = extractValue(fileContent, 'android', 'apiKey');
  final androidAppId = extractValue(fileContent, 'android', 'appId');
  final messagingSenderId = extractValue(fileContent, 'android', 'messagingSenderId');
  final projectId = extractValue(fileContent, 'android', 'projectId');
  final storageBucket = extractValue(fileContent, 'android', 'storageBucket');
  final androidClientId = extractValue(fileContent, 'android', 'androidClientId');

  // Extract iOS configuration
  final iosApiKey = extractValue(fileContent, 'ios', 'apiKey');
  final iosAppId = extractValue(fileContent, 'ios', 'appId');
  final iosClientId = extractValue(fileContent, 'ios', 'iosClientId');
  final iosBundleId = extractValue(fileContent, 'ios', 'iosBundleId');

  // Generate environment variable entries
  final envEntries = '''
# Firebase Configuration - Extracted from $filePath
FIREBASE_ANDROID_API_KEY=$androidApiKey
FIREBASE_ANDROID_APP_ID=$androidAppId
FIREBASE_IOS_API_KEY=$iosApiKey
FIREBASE_IOS_APP_ID=$iosAppId
FIREBASE_MESSAGING_SENDER_ID=$messagingSenderId
FIREBASE_PROJECT_ID=$projectId
FIREBASE_STORAGE_BUCKET=$storageBucket
FIREBASE_ANDROID_CLIENT_ID=${androidClientId ?? ''}
FIREBASE_IOS_CLIENT_ID=${iosClientId ?? ''}
FIREBASE_IOS_BUNDLE_ID=${iosBundleId ?? ''}
''';

  print('Firebase configuration extracted from $filePath:');
  print(envEntries);

  // Ask if the user wants to append to .env file
  print('\nDo you want to append these entries to .${environment}.env? (y/n)');
  final response = stdin.readLineSync()?.toLowerCase();

  if (response == 'y' || response == 'yes') {
    final envFile = File('.${environment}.env');
    if (await envFile.exists()) {
      await envFile.writeAsString('\n$envEntries', mode: FileMode.append);
      print('Entries appended to .${environment}.env');
    } else {
      print('Error: .${environment}.env file does not exist');
    }
  }
}

String? extractValue(String content, String platform, String key) {
  final regex = RegExp('static const FirebaseOptions $platform = FirebaseOptions\\(\\s*(?:.*?,\\s*)*?$key: \'([^\']*)\'');
  final match = regex.firstMatch(content);
  return match?.group(1);
}