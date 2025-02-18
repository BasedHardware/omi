import 'dart:convert';
import 'dart:math';
import 'package:crypto/crypto.dart';
import 'package:friend_private/backend/preferences.dart';
import 'package:http/http.dart' as http;
import 'package:oauth1/oauth1.dart' as oauth1;
import 'package:flutter/foundation.dart';
import 'package:cloud_firestore/cloud_firestore.dart';
import 'package:firebase_auth/firebase_auth.dart';

class TwitterApiService {
  final FirebaseFirestore _firestore = FirebaseFirestore.instance;
  final FirebaseAuth _auth = FirebaseAuth.instance;
  
  // Your app's credentials
  static const String _apiKey = 'hlSXpzpGbuD39MXhUxgRBBQBY';
  static const String _apiSecret = 'MwcBCAnZhdo0QXcSIpasxJM8bGEZSrtGNG5WyVU6xSUsp8J83L';

  // Encryption key generation for message content
  String generateEncryptionKey() {
    final random = Random.secure();
    final bytes = List<int>.generate(32, (i) => random.nextInt(256));
    return base64.encode(bytes);
  }

  // Encrypt message content
  String encryptMessage(String message, String key) {
    final bytes = utf8.encode(message);
    final keyBytes = base64.decode(key);
    final encrypted = List<int>.generate(bytes.length, (i) => bytes[i] ^ keyBytes[i % keyBytes.length]);
    return base64.encode(encrypted);
  }

  // Decrypt message content
  String decryptMessage(String encryptedMessage, String key) {
    final bytes = base64.decode(encryptedMessage);
    final keyBytes = base64.decode(key);
    final decrypted = List<int>.generate(bytes.length, (i) => bytes[i] ^ keyBytes[i % keyBytes.length]);
    return utf8.decode(decrypted);
  }

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


  Future<void> postTweetV2({
    required String tweetText,
  }) async {
    try {
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

  Future<Map<String, dynamic>> getDMEvents() async {
    try {
      final userAccessToken = SharedPreferencesUtil().twitterAccessToken;
      final userAccessSecret = SharedPreferencesUtil().twitterAccessTokenSecret;
      final currentUser = _auth.currentUser;

      if (currentUser == null) {
        throw Exception('User not authenticated');
      }

      if (userAccessToken.isEmpty || userAccessSecret.isEmpty) {
        throw Exception('Twitter access tokens not found. Please sign in first.');
      }

      // Create OAuth 1.0a credentials
      final platform = oauth1.Platform(
        'https://api.twitter.com/oauth/request_token',
        'https://api.twitter.com/oauth/access_token',
        'https://api.twitter.com/oauth/authorize',
        oauth1.SignatureMethods.hmacSha1,
      );

      final clientCredentials = oauth1.ClientCredentials(_apiKey, _apiSecret);
      final credentials = oauth1.Credentials(userAccessToken, userAccessSecret);
      final client = oauth1.Client(oauth1.SignatureMethods.hmacSha1, clientCredentials, credentials);

      // Enhanced URL with additional fields and expansions
      final url = Uri.parse(
        'https://api.twitter.com/2/dm_events'
        '?event_types=MessageCreate'
        '&expansions=sender_id,participant_ids,attachments.media_keys'
        '&dm_event.fields=attachments,created_at,dm_conversation_id,entities,event_type,id,participant_ids,sender_id,text'
        '&user.fields=name,username,verified,profile_image_url,description'
        '&max_results=100'
      );
      
      final response = await client.get(url);
      
      // Clean up
      client.close();

      if (response.statusCode == 200) {
        final data = json.decode(response.body);
        final processedData = await _processDMEventsAndStore(data, currentUser.uid);
        return processedData;
      } else {
        throw Exception('Failed to fetch DM events: ${response.statusCode} => ${response.body}');
      }
    } catch (e) {
      rethrow;
    }
  }

  Future<Map<String, dynamic>> _processDMEventsAndStore(Map<String, dynamic> rawData, String userId) async {
    try {
      final List<dynamic> events = rawData['data'] ?? [];
      final List<dynamic> users = rawData['includes']?['users'] ?? [];
      
      // Create a map of user information for quick lookup
      final Map<String, Map<String, dynamic>> userInfo = {};
      for (var user in users) {
        userInfo[user['id']] = {
          'name': user['name'],
          'username': user['username'],
          'verified': user['verified'] ?? false,
          'profile_image_url': user['profile_image_url'],
          'description': user['description'],
        };
      }

      final encryptionKey = generateEncryptionKey();
      
      // Process each DM event with enhanced user information
      final processedEvents = await Future.wait(events.map((event) async {
        final List<String> participantIds = List<String>.from(event['participant_ids'] ?? []);
        // Sort participant IDs to ensure consistent ordering
        participantIds.sort();
        
        final isGroupDM = participantIds.length > 2;
        
        // Create conversation metadata
        final conversationMetadata = {
          'is_group_dm': isGroupDM,
          'participant_count': participantIds.length,
          'conversation_name': isGroupDM 
              ? _generateGroupName(participantIds.map((id) => userInfo[id]?['name']?.toString() ?? '').toList())
              : null,
        };

        final eventData = {
          'id': event['id'],
          'text': encryptMessage(event['text'], encryptionKey),
          'sender_id': event['sender_id'],
          'sender_info': userInfo[event['sender_id']] ?? {},
          'participant_ids': participantIds, // Now sorted
          'participant_info': participantIds.map((id) => userInfo[id] ?? {}).toList(),
          'conversation_metadata': conversationMetadata,
          'event_type': event['event_type'],
          'created_at': event['created_at'],
          'dm_conversation_id': event['dm_conversation_id'],
          'entities': event['entities'],
          'attachments': event['attachments'],
          'encryption_key': encryptionKey,
          'user_id': userId,
          'timestamp': FieldValue.serverTimestamp(),
        };

        // Store in Firestore with security rules
        await _firestore
          .collection('users')
          .doc(userId)
          .collection('twitter_messages')
          .doc(event['id'])
          .set(eventData, SetOptions(merge: true));

        // Return decrypted version for immediate use
        return {
          'id': event['id'],
          'text': event['text'],
          'sender_id': event['sender_id'],
          'sender_info': userInfo[event['sender_id']] ?? {},
          'participant_ids': participantIds,
          'participant_info': participantIds.map((id) => userInfo[id] ?? {}).toList(),
          'conversation_metadata': conversationMetadata,
          'event_type': event['event_type'],
          'created_at': event['created_at'],
          'dm_conversation_id': event['dm_conversation_id'],
          'entities': event['entities'],
          'attachments': event['attachments'],
        };
      }));

      // Group DMs by conversation using dm_conversation_id instead of participant_ids
      final Map<String, List<dynamic>> conversationGroups = {};
      
      for (var event in processedEvents) {
        final conversationId = event['dm_conversation_id'] ?? 
            _generateConversationKey(
              (event['participant_ids'] as List).map((id) => id.toString()).toList()
            );
        
        if (!conversationGroups.containsKey(conversationId)) {
          conversationGroups[conversationId] = [];
        }
        conversationGroups[conversationId]!.add(event);
      }

      // Add conversation metadata to the response
      final Map<String, Map<String, dynamic>> conversationMetadata = {};
      for (var entry in conversationGroups.entries) {
        final events = entry.value;
        if (events.isNotEmpty) {
          final firstEvent = events.first;
          conversationMetadata[entry.key] = {
            'is_group_dm': firstEvent['conversation_metadata']['is_group_dm'],
            'participant_count': firstEvent['conversation_metadata']['participant_count'],
            'conversation_name': firstEvent['conversation_metadata']['conversation_name'],
            'last_message_at': events.first['created_at'],
            'message_count': events.length,
            'participants': firstEvent['participant_info'],
          };
        }
      }

      return {
        'events': processedEvents,
        'conversations': conversationGroups,
        'conversation_metadata': conversationMetadata,
        'total_count': events.length,
        'users': userInfo,
      };
    } catch (e) {
      return {
        'events': [],
        'conversations': {},
        'conversation_metadata': {},
        'total_count': 0,
        'users': {},
        'error': e.toString()
      };
    }
  }

  // Helper method to generate a consistent conversation key
  String _generateConversationKey(List<String> participantIds) {
    // Sort to ensure consistent ordering
    participantIds.sort();
    return participantIds.join('-');
  }

  // Helper method to generate a group conversation name
  String _generateGroupName(List<String> participantNames) {
    if (participantNames.isEmpty) return 'Group Conversation';
    if (participantNames.length <= 3) {
      return participantNames.join(', ');
    }
    return '${participantNames.take(3).join(', ')} +${participantNames.length - 3}';
  }

  // Method to retrieve messages from Firestore
  Future<List<Map<String, dynamic>>> getStoredMessages() async {
    try {
      final currentUser = _auth.currentUser;
      if (currentUser == null) {
        throw Exception('User not authenticated');
      }

      final messagesSnapshot = await _firestore
          .collection('users')
          .doc(currentUser.uid)
          .collection('twitter_messages')
          .orderBy('timestamp', descending: true)
          .get();

      return messagesSnapshot.docs.map((doc) {
        final data = doc.data();
        String decryptedText = '';
        try {
          if (data['text'] != null && data['encryption_key'] != null) {
            decryptedText = decryptMessage(
              data['text'] as String,
              data['encryption_key'] as String
            );
          }
        } catch (e) {
          // Silently handle decryption errors and continue with empty text
        }

        // Safely extract participant information
        final List<String> participantIds = (data['participant_ids'] as List?)
            ?.map((id) => id.toString())
            .toList() ?? [];
        
        final List<Map<String, dynamic>> participantInfo = 
            (data['participant_info'] as List?)
            ?.map((info) => Map<String, dynamic>.from(info))
            .toList() ?? [];

        // Safely extract sender information
        final Map<String, dynamic> senderInfo = 
            Map<String, dynamic>.from(data['sender_info'] as Map? ?? {});

        // Safely extract conversation metadata
        final Map<String, dynamic> conversationMetadata = 
            Map<String, dynamic>.from(data['conversation_metadata'] as Map? ?? {});

        // Safely extract entities and attachments
        final Map<String, dynamic> entities = 
            Map<String, dynamic>.from(data['entities'] as Map? ?? {});
        final Map<String, dynamic> attachments = 
            Map<String, dynamic>.from(data['attachments'] as Map? ?? {});
        
        return {
          'id': data['id'] ?? doc.id,
          'text': decryptedText,
          'sender_id': data['sender_id'] ?? '',
          'sender_info': senderInfo,
          'participant_ids': participantIds,
          'participant_info': participantInfo,
          'conversation_metadata': conversationMetadata,
          'event_type': data['event_type'] ?? 'message',
          'created_at': data['created_at'] ?? DateTime.now().toIso8601String(),
          'dm_conversation_id': data['dm_conversation_id'],
          'entities': entities,
          'attachments': attachments,
        };
      }).toList();
    } catch (e) {
      rethrow;
    }
  }
} 