import 'dart:convert';
import 'dart:math';
import 'package:crypto/crypto.dart';
import 'package:friend_private/backend/preferences.dart';
import 'package:http/http.dart' as http;
import 'package:oauth1/oauth1.dart' as oauth1;
import 'package:flutter/foundation.dart';

class TwitterApiService {
  static const String _baseUrl = 'https://api.twitter.com/1.1';
  
  // Your app's credentials
  static final String _apiKey = '8wB9Lv27KxTaLIVH2ScKnMyiF';
  static final String _apiSecret = '7RwwB6WmPmVkxb2i8MCfFgmITHPzvTYmt2jTYkbQOfuQ5SmtJU';

  static String _generateNonce() {
    const chars = 'abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789';
    final random = Random.secure();
    return List.generate(32, (index) => chars[random.nextInt(chars.length)]).join();
  }

  static String _generateTimestamp() {
    return (DateTime.now().millisecondsSinceEpoch ~/ 1000).toString();
  }

  static String _percentEncode(String str) {
    return Uri.encodeComponent(str)
        .replaceAll('*', '%2A')
        .replaceAll('!', '%21')
        .replaceAll('\'', '%27')
        .replaceAll('(', '%28')
        .replaceAll(')', '%29');
  }

  static String _generateSignature(
    String method,
    String url,
    Map<String, String> parameters,
    String consumerSecret,
    String tokenSecret,
  ) {
    final sortedParams = Map.fromEntries(
      parameters.entries.toList()..sort((a, b) => a.key.compareTo(b.key))
    );

    final paramString = sortedParams.entries
        .map((e) => '${_percentEncode(e.key)}=${_percentEncode(e.value)}')
        .join('&');

    final signatureBase = [
      method,
      _percentEncode(url),
      _percentEncode(paramString),
    ].join('&');

    final signingKey = '$consumerSecret&$tokenSecret';
    final hmac = Hmac(sha1, utf8.encode(signingKey));
    final digest = hmac.convert(utf8.encode(signatureBase));
    return base64.encode(digest.bytes);
  }

  static Future<bool> postTweet(String tweetText) async {
    try {
      final prefs = SharedPreferencesUtil();
      final accessToken = prefs.twitterAccessToken;
      final accessTokenSecret = prefs.twitterAccessTokenSecret;

      if (accessToken.isEmpty || accessTokenSecret.isEmpty) {
        print('Twitter tokens not found');
        return false;
      }

      final url = '$_baseUrl/statuses/update.json';
      final nonce = _generateNonce();
      final timestamp = _generateTimestamp();

      final parameters = {
        'status': tweetText,
        'oauth_consumer_key': _apiKey,
        'oauth_nonce': nonce,
        'oauth_signature_method': 'HMAC-SHA1',
        'oauth_timestamp': timestamp,
        'oauth_token': accessToken,
        'oauth_version': '1.0',
      };

      final signature = _generateSignature(
        'POST',
        url,
        parameters,
        _apiSecret,
        accessTokenSecret,
      );

      final authHeader = 'OAuth ' +
          [
            'oauth_consumer_key="$_apiKey"',
            'oauth_nonce="$nonce"',
            'oauth_signature="${_percentEncode(signature)}"',
            'oauth_signature_method="HMAC-SHA1"',
            'oauth_timestamp="$timestamp"',
            'oauth_token="$accessToken"',
            'oauth_version="1.0"',
          ].join(', ');

      final response = await http.post(
        Uri.parse(url),
        headers: {
          'Authorization': authHeader,
          'Content-Type': 'application/x-www-form-urlencoded',
        },
        body: {'status': tweetText},
      );

      print('Twitter API Response: ${response.statusCode}');
      print('Response body: ${response.body}');

      if (response.statusCode == 200) {
        final responseData = json.decode(response.body);
        print('Tweet posted successfully: ${responseData['id_str']}');
        return true;
      } else {
        print('Failed to post tweet: ${response.statusCode}');
        return false;
      }
    } catch (e) {
      print('Error posting tweet: $e');
      return false;
    }
  }

  Future<void> postTweetV2({
    required String tweetText,
  }) async {
    try {
      print('Posting tweet v2.. consumerKey: $_apiKey');
      print('Posting tweet v2.. consumerSecret: $_apiSecret');
      print('Posting tweet v2.. userAccessToken: ${SharedPreferencesUtil().twitterAccessToken}');
      print('Posting tweet v2.. userAccessSecret: ${SharedPreferencesUtil().twitterAccessTokenSecret}');
      await _postTweetV2(
        consumerKey: _apiKey,
        consumerSecret: _apiSecret,
        userAccessToken: SharedPreferencesUtil().twitterAccessToken,
        userAccessSecret: SharedPreferencesUtil().twitterAccessTokenSecret,
        tweetText: tweetText,
      );
    } catch (e) {
      debugPrint('Error posting tweet: $e');
      rethrow;
    }
  }

  Future<void> _postTweetV2({
    required String consumerKey,
    required String consumerSecret,
    required String userAccessToken,
    required String userAccessSecret,
    required String tweetText,
  }) async {
    // Create an OAuth1 "platform"
    final platform = oauth1.Platform(
      'https://api.twitter.com/oauth/request_token',
      'https://api.twitter.com/oauth/access_token',
      'https://api.twitter.com/oauth/authorize',
      oauth1.SignatureMethods.hmacSha1,
    );

    // App credentials
    final clientCredentials = oauth1.ClientCredentials(
      consumerKey,
      consumerSecret,
    );

    // User's token/secret
    final credentials = oauth1.Credentials(
      userAccessToken,
      userAccessSecret,
    );

    print('Posting tweet v2.. consumerKey: $consumerKey');
    print('Posting tweet v2.. consumerSecret: $consumerSecret');
    print('Posting tweet v2.. userAccessToken: $userAccessToken');
    print('Posting tweet v2.. userAccessSecret: $userAccessSecret');
    print('Posting tweet v2.. clientCredentials: $clientCredentials');
    print('Posting tweet v2.. credentials: $credentials');

    // Build a signed HTTP client
    final client = oauth1.Client(oauth1.SignatureMethods.hmacSha1, clientCredentials, credentials);
    print('Posting tweet v2.. client: $client');

    final url = Uri.parse('https://api.twitter.com/2/tweets');

    // Prepare the JSON body with your tweet text
    final body = jsonEncode({
      "text": tweetText,
    });
    print('Posting tweet v2.. body: $body');

    // Send a POST request
    final response = await client.post(
      url,
      headers: {'Content-Type': 'application/json'},
      body: body,
    );

    // Clean up
    client.close();

    if (response.statusCode == 201 || response.statusCode == 200) {
      // 201 is "Created" per Twitter's docs, though sometimes 200 might appear
      debugPrint('Tweet posted: ${response.body}');
    } else {
      debugPrint('Error posting tweet: ${response.statusCode}');
      debugPrint(response.body);
      throw Exception('Tweet failed: ${response.statusCode} => ${response.body}');
    }
  }
} 