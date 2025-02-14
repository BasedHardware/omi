import 'dart:convert';
import 'package:http/http.dart' as http;
import 'package:friend_private/backend/preferences.dart';

class TwitterVerificationService {
  static const String _baseUrl = 'https://api.socialdata.tools/twitter';
  static const String _apiKey = '2120|7dUI7UujUbcFK9mLr9MAxrxsRRKnszu5z6x6Xm3J799b88a9'; // We'll replace this with the actual key

  /// Check if the user is already verified
  static bool isVerified(String username) {
    final prefs = SharedPreferencesUtil();
    final normalizedUsername = username.replaceAll('@', '').toLowerCase();
    final storedUsername = prefs.verifiedTwitterHandle.replaceAll('@', '').toLowerCase();
    
    // If the stored username matches and is verified
    if (prefs.isTwitterVerified && normalizedUsername == storedUsername) {
      return true;
    }
    return false;
  }

  /// Save the verification state
  static void _saveVerificationState(String username) {
    final prefs = SharedPreferencesUtil();
    final normalizedUsername = username.replaceAll('@', '');
    
    prefs.isTwitterVerified = true;
    prefs.verifiedTwitterHandle = normalizedUsername;
    prefs.twitterVerificationTimestamp = DateTime.now().millisecondsSinceEpoch;
  }

  static Future<bool> verifyTweet(String username) async {
    try {
      // Check if already verified
      if (isVerified(username)) {
        return true;
      }

      // Normalize the username and create the search query
      final normalizedUsername = username.replaceAll('@', '');
      final searchQuery = Uri.encodeComponent('from:$normalizedUsername "Verifying my clone: omi.me/$normalizedUsername"');
      
      // Search for the verification tweet
      final response = await http.get(
        Uri.parse('$_baseUrl/search?query=$searchQuery&type=Latest'),
        headers: {
          'Authorization': 'Bearer $_apiKey',
          'Accept': 'application/json',
        },
      );

      if (response.statusCode == 200) {
        final data = json.decode(response.body);
        final tweets = data['tweets'] as List<dynamic>;

        // If we found any tweets matching our search query, the user is verified
        if (tweets.isNotEmpty) {
          // Save verification state
          _saveVerificationState(normalizedUsername);
          return true;
        }
      } else if (response.statusCode == 402) {
        throw Exception('API credit limit exceeded');
      } else if (response.statusCode == 500) {
        throw Exception('Twitter API service unavailable');
      }
      
      return false;
    } catch (e) {
      print('Error verifying tweet: $e');
      rethrow; // Rethrow to handle specific errors in the UI
    }
  }

  /// Reset verification state (useful for testing or manual reset)
  static void resetVerification() {
    final prefs = SharedPreferencesUtil();
    prefs.isTwitterVerified = false;
    prefs.verifiedTwitterHandle = '';
    prefs.twitterVerificationTimestamp = 0;
  }

  static Future<String?> getUserId(String username) async {
    try {
      // This is a placeholder - you'll need to implement user ID lookup
      // You might want to use a different endpoint to get the user ID first
      return null;
    } catch (e) {
      print('Error getting user ID: $e');
      return null;
    }
  }
} 