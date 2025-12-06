import 'dart:io';
import 'package:flutter/foundation.dart';
import 'package:http/http.dart' as http;
import 'package:omi/backend/http/shared.dart';
import 'package:omi/backend/preferences.dart';

/// Upload Pocket MP3 file to backend for conversion
Future<bool> uploadPocketMp3({
  required String filePath,
  required String deviceId,
  required int timerStart,
}) async {
  try {
    debugPrint('Uploading Pocket MP3: $filePath');
    
    final file = File(filePath);
    if (!await file.exists()) {
      debugPrint('MP3 file not found: $filePath');
      return false;
    }
    
    final fileBytes = await file.readAsBytes();
    final fileName = filePath.split('/').last;
    
    final url = Uri.parse('${getApiBaseUrl()}/v1/pocket/upload-mp3');
    
    final request = http.MultipartRequest('POST', url);
    request.headers['Authorization'] = await getAuthHeader();
    
    // Add file
    request.files.add(http.MultipartFile.fromBytes(
      'file',
      fileBytes,
      filename: fileName,
    ));
    
    // Add metadata
    request.fields['device_id'] = deviceId;
    request.fields['timer_start'] = timerStart.toString();
    
    debugPrint('Sending MP3 upload request to: $url');
    final response = await request.send();
    final responseBody = await response.stream.bytesToString();
    
    if (response.statusCode == 200) {
      debugPrint('MP3 upload successful: $fileName');
      return true;
    } else {
      debugPrint('MP3 upload failed: ${response.statusCode} - $responseBody');
      return false;
    }
  } catch (e) {
    debugPrint('Error uploading MP3: $e');
    return false;
  }
}
