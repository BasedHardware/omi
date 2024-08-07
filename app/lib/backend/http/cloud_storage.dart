import 'dart:convert';
import 'dart:io';

import 'package:flutter/material.dart';
import 'package:friend_private/backend/preferences.dart';
import 'package:googleapis_auth/auth_io.dart';
import 'package:http/http.dart' as http;
import 'package:googleapis/drive/v3.dart' as drive;
import 'package:google_sign_in/google_sign_in.dart';
import 'package:google_sign_in/google_sign_in.dart';
import 'package:googleapis/drive/v3.dart' as drive;
import 'package:googleapis_auth/auth_io.dart';

AuthClient? authClient;
drive.DriveApi? driveApi;

Future<void> authenticateGCP({String? base64}) async {
  var credentialsBase64 = base64 ?? SharedPreferencesUtil().gcpCredentials;
  if (credentialsBase64.isEmpty) {
    debugPrint('No GCP credentials found');
    return;
  }
  final credentialsBytes = base64Decode(credentialsBase64);
  String decodedString = utf8.decode(credentialsBytes);
  final credentials = ServiceAccountCredentials.fromJson(jsonDecode(decodedString));
  var scopes = ['https://www.googleapis.com/auth/devstorage.full_control'];
  authClient = await clientViaServiceAccount(credentials, scopes);
  debugPrint('Authenticated');
}

Future<void> authenticateGoogleDrive() async {
  final googleSignIn = GoogleSignIn.standard(scopes: [drive.DriveApi.driveFileScope]);
  final account = await googleSignIn.signIn();
  if (account == null) {
    debugPrint('Google sign-in failed');
    return;
  }
  final authHeaders = await account.authHeaders;
  final authenticateClient = GoogleAuthClient(authHeaders);
  driveApi = drive.DriveApi(authenticateClient);
  debugPrint('Google Drive authenticated');
}

Future<String?> uploadFile(File file, {bool prefixTimestamp = false}) async {
  String bucketName = SharedPreferencesUtil().gcpBucketName;
  if (bucketName.isEmpty) {
    debugPrint('No bucket name found');
    return null;
  }
  String fileName = file.path.split('/')[file.path.split('/').length - 1];
  if (prefixTimestamp) {
    fileName = '${DateTime.now().millisecondsSinceEpoch}_$fileName';
  }
  String url = 'https://storage.googleapis.com/upload/storage/v1/b/$bucketName/o?uploadType=media&name=$fileName';

  try {
    var response = await http.post(
      Uri.parse(url),
      headers: {
        'Authorization': 'Bearer ${authClient?.credentials.accessToken.data}',
        'Content-Type': 'audio/wav',
      },
      body: file.readAsBytesSync(),
    );

    if (response.statusCode == 200) {
      var json = jsonDecode(response.body);
      debugPrint(json.toString());
      debugPrint('Upload successful');
      return fileName;
    } else {
      debugPrint('Failed to upload: ${response.body}');
    }
  } catch (e) {
    debugPrint('Error uploading file: $e');
  }
  return null;
}

Future<String?> uploadFileToGoogleDrive(File file, String folderId) async {
  if (driveApi == null) {
    debugPrint('Google Drive API is not authenticated');
    return null;
  }

  String fileName = file.path.split('/').last;
  var media = drive.Media(file.openRead(), file.lengthSync());
  var driveFile = drive.File()
    ..name = fileName
    ..parents = [folderId];

  try {
    var response = await driveApi!.files.create(driveFile, uploadMedia: media);
    debugPrint('Upload to Google Drive successful: ${response.id}');
    return response.id;
  } catch (e) {
    debugPrint('Error uploading file to Google Drive: $e');
  }
  return null;
}

// Download file method
// Future<File?> downloadFile(String objectName, String saveFileName) async {
//   final directory = await getApplicationDocumentsDirectory();
//   String saveFilePath = '${directory.path}/$saveFileName';
//   if (File(saveFilePath).existsSync()) {
//     debugPrint('File already exists: $saveFileName');
//     return File(saveFilePath);
//   }
//
//   String bucketName = SharedPreferencesUtil().gcpBucketName;
//   if (bucketName.isEmpty) {
//     debugPrint('No bucket name found');
//     return null;
//   }
//
//   try {
//     var response = await http.get(
//       Uri.parse('https://storage.googleapis.com/storage/v1/b/$bucketName/o/$objectName?alt=media'),
//       headers: {'Authorization': 'Bearer ${authClient?.credentials.accessToken.data}'},
//     );
//
//     if (response.statusCode == 200) {
//       final file = File('${directory.path}/$saveFileName');
//       await file.writeAsBytes(response.bodyBytes);
//       debugPrint('Download successful: $saveFileName');
//       return file;
//     } else {
//       debugPrint('Failed to download: ${response.body}');
//     }
//   } catch (e) {
//     debugPrint('Error downloading file: $e');
//   }
//   return null;
// }

class GoogleAuthClient extends http.BaseClient {
  final Map<String, String> _headers;
  final http.Client _client = http.Client();

  GoogleAuthClient(this._headers);

  @override
  Future<http.StreamedResponse> send(http.BaseRequest request) {
    return _client.send(request..headers.addAll(_headers));
  }
}
