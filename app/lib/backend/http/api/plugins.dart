import 'dart:convert';

import 'package:friend_private/backend/http/shared.dart';
import 'package:friend_private/backend/preferences.dart';
import 'package:friend_private/backend/schema/plugin.dart';
import 'package:friend_private/env/env.dart';
import 'package:instabug_flutter/instabug_flutter.dart';

Future<List<Plugin>> retrievePlugins() async {
  // Log request details
  final url = '${Env.apiBaseUrl}v2/plugins';
  print('retrievePlugins Request URL: $url');
  print('retrievePlugins Request Method: GET');
  print('retrievePlugins Request Headers: {}');

  var response = await makeApiCall(
    url: url,
    headers: {},
    body: '',
    method: 'GET',
  );

  print('retrievePlugins Response Status Code: ${response?.statusCode}');
  print('retrievePlugins Response Body: ${response?.body}');
  // Check the response status and log response data
  if (response?.statusCode == 200) {
    try {
      // Attempt to decode the response and parse plugins
      var plugins = Plugin.fromJsonList(jsonDecode(response!.body));
      // Save the plugin list to shared preferences
      SharedPreferencesUtil().pluginsList = plugins;
      // Log the response body
      print('retrievePlugins Response Body: ${response.body}');

      return plugins;
    } catch (e, stackTrace) {
      // Log the error and stack trace
      print('retrievePlugins Error: $e');
      CrashReporting.reportHandledCrash(e, stackTrace);

      // Return the saved plugin list from shared preferences in case of error
      return SharedPreferencesUtil().pluginsList;
    }
  } else {
    // Log the response status code and body in case of error
    print(
        'retrievePlugins Failed Response Status Code: ${response?.statusCode}');
    print('retrievePlugins Failed Response Body: ${response?.body}');
  }

  // Return the saved plugin list from shared preferences if the response is not successful
  return SharedPreferencesUtil().pluginsList;
}

Future<bool> enablePluginServer(String pluginId) async {
  // Log request details
  final url = '${Env.apiBaseUrl}v1/plugins/enable?plugin_id=$pluginId';
  print('enablePluginServer Request URL: $url');
  print('enablePluginServer Request Method: POST');
  print(
      'enablePluginServer Request Headers: {}'); // Replace with actual headers if needed
  print('enablePluginServer Request Body: '); // No body in this case

  // Make the API call
  var response = await makeApiCall(
    url: url,
    headers: {},
    method: 'POST',
    body: '',
  );

  // Log response details
  if (response == null) {
    print("enablePluginServer: Failed to get a response");
    return false;
  }
  print("enablePluginServer Response Status Code: ${response.statusCode}");
  print("enablePluginServer Response Body: ${response.body}");

  // Return true if the status code is 200, otherwise return false
  return response.statusCode == 200;
}

Future<bool> disablePluginServer(String pluginId) async {
  // Log the request details
  final url = '${Env.apiBaseUrl}v1/plugins/disable?plugin_id=$pluginId';
  print('disablePluginServer Request URL: $url');
  print('disablePluginServer Request Method: POST');
  print(
      'disablePluginServer Request Headers: {}'); // Replace with actual headers if needed
  print('disablePluginServer Request Body: '); // Empty body in this case

  // Make the API call
  var response = await makeApiCall(
    url: url,
    headers: {},
    method: 'POST',
    body: '',
  );

  // Check if response is null and log the response status code
  if (response == null) {
    print("disablePluginServer: No response received.");
    return false;
  }

  // Log the response status code and body
  print("disablePluginServer Response Status Code: ${response.statusCode}");
  print("disablePluginServer Response Body: ${response.body}");

  // Return true if the response status code is 200, otherwise return false
  return response.statusCode == 200;
}

Future<void> reviewPlugin(String pluginId, double score,
    {String review = ''}) async {
  // Log the request details
  final url = '${Env.apiBaseUrl}v1/plugins/review?plugin_id=$pluginId';
  final requestBody = jsonEncode({'score': score, 'review': review});

  print('reviewPlugin Request URL: $url');
  print('reviewPlugin Request Method: POST');
  print('reviewPlugin Request Headers: {Content-Type: application/json}');
  print('reviewPlugin Request Body: $requestBody');

  // Make the API call
  var response = await makeApiCall(
    url: url,
    headers: {'Content-Type': 'application/json'},
    method: 'POST',
    body: requestBody,
  );

  // Check if response is null and log the response body
  if (response == null) {
    print("reviewPlugin: No response received.");
    return;
  }

  // Log the response body
  print('reviewPlugin Response Status Code: ${response.statusCode}');
  print('reviewPlugin Response Body: ${response.body}');
}

Future<void> migrateUserServer(String prevUid, String newUid) async {
  // Log the request details
  final url = '${Env.apiBaseUrl}migrate-user?prev_uid=$prevUid&new_uid=$newUid';

  print('migrateUserServer Request URL: $url');
  print('migrateUserServer Request Method: POST');
  print(
      'migrateUserServer Request Headers: {}'); // Replace with actual headers if needed
  print('migrateUserServer Request Body: '); // Empty body for this request

  // Make the API call
  var response = await makeApiCall(
    url: url,
    headers: {},
    method: 'POST',
    body: '',
  );

  // Check if response is null and log the response body
  if (response == null) {
    print("migrateUserServer: No response received.");
    return;
  }

  // Log the response status code and body
  print('migrateUserServer Response Status Code: ${response.statusCode}');
  print('migrateUserServer Response Body: ${response.body}');
}

Future<String> getPluginMarkdown(String pluginMarkdownPath) async {
  // Construct the complete URL
  // https://raw.githubusercontent.com/BasedHardware/Friend/main/assets/external_plugins_instructions/notion-conversations-crm.md
  final url =
      'https://raw.githubusercontent.com/BasedHardware/Friend/main$pluginMarkdownPath';

  // Log the request details
  print('getPluginMarkdown Request URL: $url');
  print('getPluginMarkdown Request Method: GET');
  print('getPluginMarkdown Request Headers: {}'); // No headers in this case

  // Make the API call
  var response = await makeApiCall(
    url: url,
    method: 'GET',
    headers: {},
    body: '',
  );

  // Check if response is null and log the response body
  if (response == null) {
    print("getPluginMarkdown: No response received.");
    return '';
  }

  // Log the response status code and body
  print('getPluginMarkdown Response Status Code: ${response.statusCode}');
  print('getPluginMarkdown Response Body: ${response.body}');

  // Return the response body or an empty string if the response is null
  return response.body ?? '';
}

Future<bool> isPluginSetupCompleted(String? url) async {
  // Check if the URL is null or empty, and log the early exit
  if (url == null || url.isEmpty) {
    print('isPluginSetupCompleted: URL is null or empty, returning true.');
    return true;
  }

  // Log the request details
  final requestUrl = '$url?uid=${SharedPreferencesUtil().uid}';
  print('isPluginSetupCompleted Request URL: $requestUrl');
  print('isPluginSetupCompleted Request Method: GET');
  print(
      'isPluginSetupCompleted Request Headers: {}'); // No headers in this case

  // Make the API call
  var response = await makeApiCall(
    url: requestUrl,
    method: 'GET',
    headers: {},
    body: '',
  );

  // Check if the response is null
  if (response == null) {
    print('isPluginSetupCompleted: No response received.');
    return false;
  }

  // Log the response status code and body
  print('isPluginSetupCompleted Response Status Code: ${response.statusCode}');
  print('isPluginSetupCompleted Response Body: ${response.body}');

  // Decode the response body
  var data;
  try {
    data = jsonDecode(response.body);
  } catch (e) {
    print('isPluginSetupCompleted: Error decoding JSON - $e');
    return false;
  }

  // Log the decoded response data
  print('isPluginSetupCompleted Decoded Data: $data');

  // Return the value of `is_setup_completed` or false if it is not found
  return data['is_setup_completed'] ?? false;
}

/// Subscription Plugins
Future<List<Product>> subscriptionsProductsOld() async {
  // Log request details
  //final url = '${Env.apiBaseUrl}v2/plugins';
  const url = 'https://api.rechargeapps.com/products';
  print('subscriptionsProducts Request URL: $url');

  var response = await makeApiCall(
    url: url,
    headers: {'X-Recharge-Access-Token': '${Env.rechargeAppApiKey}'},
    body: '',
    method: 'GET',
  );

  print('subscriptionsProducts Response Status Code: ${response?.statusCode}');
  print('subscriptionsProducts Response Body: ${response?.body}');
  // Check the response status and log response data
  if (response?.statusCode == 200) {
    try {
      // Attempt to decode the response and parse plugins
      var data = jsonDecode(response!.body);
      List<Product> products = (data['products'] as List)
          .map((productJson) => Product.fromJson(productJson))
          .toList();

      ///var products = Product.fromJsonList(data['products']);
      // Save the plugin list to shared preferences
      SharedPreferencesUtil().subProductsList = products;
      // Log the response body
      print('subscriptionsProducts Response Body: ${response.body}');

      return products;
    } catch (e, stackTrace) {
      // Log the error and stack trace
      print('subscriptionsProducts Error: $e');
      CrashReporting.reportHandledCrash(e, stackTrace);

      // Return the saved plugin list from shared preferences in case of error
      return SharedPreferencesUtil().subProductsList;
    }
  } else {
    // Log the response status code and body in case of error
    print(
        'subscriptionsProducts Failed Response Status Code: ${response?.statusCode}');
    print('subscriptionsProducts Failed Response Body: ${response?.body}');
  }

  // Return the saved plugin list from shared preferences if the response is not successful
  return SharedPreferencesUtil().subProductsList;
}


