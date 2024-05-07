import 'dart:convert';
import 'dart:io';
import 'package:flutter/material.dart';
import 'package:friend_private/flutter_flow/flutter_flow_util.dart';
import 'package:shared_preferences/shared_preferences.dart';
import 'package:http/http.dart' as http;
import 'package:googleapis_auth/auth_io.dart';

AuthClient? authClient;

void authenticateGCP() async {
  var prefs = await SharedPreferences.getInstance();
  var credentialsBase64 = prefs.getString('gcpCredentials') ?? '';
  if (credentialsBase64.isEmpty) {
    debugPrint('No GCP credentials found');
    return;
  }
  final credentialsBytes = base64Decode(credentialsBase64);
  String decodedString = utf8.decode(credentialsBytes);
  debugPrint('decodedString: $decodedString');
  final credentials = ServiceAccountCredentials.fromJson(jsonDecode(decodedString));
  var scopes = ['https://www.googleapis.com/auth/devstorage.full_control'];
  authClient = await clientViaServiceAccount(credentials, scopes);
  debugPrint('Authenticated');
}

void uploadFile(File file) async {
  var prefs = await SharedPreferences.getInstance();
  String bucketName = prefs.getString('gcpBucketName') ?? '';
  if (bucketName.isEmpty) {
    debugPrint('No bucket name found');
    return;
  }
  String objectName = file.path.split('/')[file.path.split('/').length - 1];
  String url = 'https://storage.googleapis.com/upload/storage/v1/b/$bucketName/o?uploadType=media&name=$objectName';

  try {
    var response = await http.post(
      Uri.parse(url),
      headers: {
        'Authorization': 'Bearer ${authClient?.credentials.accessToken.data}',
        'Content-Type': 'type_of_your_file', // Example: 'image/jpeg'
      },
      body: file.readAsBytesSync(),
    );

    if (response.statusCode == 200) {
      var json = jsonDecode(response.body);
      debugPrint('Upload successful');
      // return json['selfLink'];
    } else {
      debugPrint('Failed to upload');
    }
  } catch (e) {
    debugPrint('Error uploading file: $e');
  }
}

// Download file method
Future<void> downloadFile(String bucketName, String objectName, String savePath) async {
  String url = 'https://storage.googleapis.com/storage/v1/b/$bucketName/o/$objectName?alt=media';

  try {
    var response = await http.get(
      Uri.parse(url),
      headers: {
        'Authorization': 'Bearer ${authClient?.credentials.accessToken.data}',
      },
    );

    if (response.statusCode == 200) {
      // Save the file to the specified path
      File saveFile = File(savePath);
      await saveFile.writeAsBytes(response.bodyBytes);
      debugPrint('Download successful: $savePath');
    } else {
      debugPrint('Failed to download: ${response.body}');
    }
  } catch (e) {
    debugPrint('Error downloading file: $e');
  }
}
