import 'dart:convert';
import 'package:http/http.dart' as http;
import 'package:flutter/material.dart';
import 'package:friend_private/pages/memories/notion/notion_oauth.dart';

class NotionService {
  // static const redirectUri = 'com.friend.ios://callback';

  // Future<String?> authenticate(BuildContext context) async {
  //   final authorizationUrl =
  //       'https://api.notion.com/v1/oauth/authorize?client_id=$clientId&response_type=code&redirect_uri=$redirectUri';

  //   final authorizationCode = await Navigator.push(
  //     context,
  //     MaterialPageRoute(
  //       builder: (context) => NotionAuthWebView(
  //         authorizationUrl: authorizationUrl,
  //         redirectUri: redirectUri,
  //       ),
  //     ),
  //   );

  //   return authorizationCode;
  // }

  // Future<String> fetchAccessToken(String authorizationCode) async {
  //   final response = await http.post(
  //     Uri.parse('https://api.notion.com/v1/oauth/token'),
  //     headers: {'Content-Type': 'application/json'},
  //     body: json.encode({
  //       'grant_type': 'authorization_code',
  //       'code': authorizationCode,
  //       'redirect_uri': redirectUri,
  //     }),
  //   );

  //   if (response.statusCode == 200) {
  //     final accessToken = json.decode(response.body)['access_token'];
  //     print('Access Token: $accessToken');
  //     return accessToken;
  //   } else {
  //     throw Exception('Failed to fetch access token');
  //   }
  // }

  // Future<void> fetchNotionData(String accessToken) async {
  //   final response = await http.get(
  //     Uri.parse('https://api.notion.com/v1/databases'),
  //     headers: {
  //       'Authorization': 'Bearer $accessToken',
  //       'Notion-Version': '2022-06-28',
  //     },
  //   );

  //   if (response.statusCode == 200) {
  //     print('Notion Data: ${response.body}');
  //   } else {
  //     throw Exception('Failed to fetch Notion data');
  //   }
  // }

  Future<String> fetchNotionData() async {
    print("dewdew");
    final response = await http.get(
      Uri.parse('https://api.notion.com/v1/databases'),
      headers: {
        'Authorization':
            'Bearer secret_G2YWyBnrFfRw37SqwrBhWJA9TnlUygzPec3F6fAxYEB',
        'Notion-Version': '2021-05-11',
      },
    );

    if (response.statusCode == 200) {
      print('Notion Data: ${response.body}');
      return response.body.toString();
    } else {
      throw Exception('Failed to fetch Notion data');
    }
  }
}
