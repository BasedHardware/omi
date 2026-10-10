import 'dart:convert';

import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:http/http.dart' as http;
import 'package:provider/provider.dart';
import 'package:shared_preferences/shared_preferences.dart';

import 'package:omi/backend/http/api/messaging_channels.dart';
import 'package:omi/backend/http/api_result.dart';
import 'package:omi/backend/preferences.dart';
import 'package:omi/env/env.dart';
import 'package:omi/l10n/app_localizations.dart';
import 'package:omi/models/subscription.dart';
import 'package:omi/providers/connectivity_provider.dart';
import 'package:omi/providers/messaging_channels_provider.dart';
import 'package:omi/providers/usage_provider.dart';
import 'package:omi/ui/ui.dart';

class ChatAppsTestEnv implements EnvFields {
  @override
  String? get apiBaseUrl => 'http://127.0.0.1:1/';

  @override
  dynamic noSuchMethod(Invocation invocation) => null;
}

Future<void> initChatAppsTest() async {
  SharedPreferences.setMockInitialValues({});
  await SharedPreferencesUtil.init();
}

const telegramEndpoint = ChatChannelEndpoint(provider: 'telegram', address: 'OmiBot');
const imessageEndpoint = ChatChannelEndpoint(provider: 'linq', address: '+15550100100');

const chatAppsOn = ChatAppsConfig(
  enabled: true,
  endpoints: {ChatChannel.telegram: telegramEndpoint, ChatChannel.imessage: imessageEndpoint},
);

final String linkIdTelegram = 'a' * 64;
final String linkIdIMessage = 'b' * 64;

Map<String, dynamic> linkJson({
  required String id,
  required String channel,
  String provider = 'telegram',
  String externalId = 'sam',
  bool visible = false,
}) =>
    {
      'id': id,
      'channel': channel,
      'provider': provider,
      'external_id': externalId,
      'visible_in_app': visible,
      'linked_at': '2026-10-10T12:00:00Z',
    };

/// A scripted `/v1/messaging/*` backend behind the [ApiSend] seam.
class FakeMessagingBackend {
  final List<ApiRequest> requests = [];
  List<Map<String, dynamic>> links = [];

  /// Status for the next calls of a method + path prefix, e.g. `POST v1/messaging/link-proofs`.
  final Map<String, int> statusFor = {};

  /// How long minted proofs live.
  Duration proofTtl = const Duration(minutes: 10);
  int _minted = 0;

  Future<http.Response> send(ApiRequest request) async {
    requests.add(request);
    final path = Uri.parse(request.url).path.replaceFirst('/', '');
    for (final entry in statusFor.entries) {
      if ('${request.method} $path'.startsWith(entry.key)) return http.Response('{"detail":"no"}', entry.value);
    }
    if (request.method == 'GET' && path == 'v1/messaging/links') {
      return http.Response(jsonEncode({'links': links}), 200);
    }
    if (request.method == 'POST' && path == 'v1/messaging/link-proofs') {
      final body = jsonDecode(request.body) as Map<String, dynamic>;
      _minted++;
      final proof =
          body['kind'] == 'code' ? '9F2C4A7B1D3E5F6${_minted % 10}0A1B2C3D4E5F6A7B' : 'tok_${_minted}_abcdefghijklmnop';
      return http.Response(
        jsonEncode({
          'proof': proof,
          'kind': body['kind'],
          'expires_at': DateTime.now().toUtc().add(proofTtl).toIso8601String(),
        }),
        200,
      );
    }
    if (path.startsWith('v1/messaging/links/')) {
      final id = path.split('/').last;
      final index = links.indexWhere((l) => l['id'] == id);
      if (index < 0) return http.Response('{"detail":"Link not found"}', 404);
      if (request.method == 'DELETE') {
        links.removeAt(index);
        return http.Response('{"status":"unlinked"}', 200);
      }
      if (request.method == 'PATCH') {
        links[index] = {...links[index], 'visible_in_app': (jsonDecode(request.body) as Map)['visible_in_app']};
        return http.Response('{"status":"updated"}', 200);
      }
    }
    return http.Response('{"detail":"Not Found"}', 404);
  }

  int count(String method, String pathPrefix) => requests
      .where((r) => r.method == method && Uri.parse(r.url).path.replaceFirst('/', '').startsWith(pathPrefix))
      .length;

  MessagingChannelsProvider provider({ChatAppsConfig config = chatAppsOn}) => MessagingChannelsProvider(
        api: MessagingChannelsApi(send: send),
        readConfig: () async => config,
      );
}

UserSubscriptionResponse subscriptionOn(PlanType plan) => UserSubscriptionResponse(
      subscription: Subscription(plan: plan, status: SubscriptionStatus.active),
      transcriptionSecondsUsed: 0,
      transcriptionSecondsLimit: 0,
      wordsTranscribedUsed: 0,
      wordsTranscribedLimit: 0,
      insightsGainedUsed: 0,
      insightsGainedLimit: 0,
    );

class StubConnectivity extends ChangeNotifier implements ConnectivityProvider {
  StubConnectivity({this.online = true});

  bool online;

  @override
  bool get isConnected => online;

  @override
  dynamic noSuchMethod(Invocation invocation) => super.noSuchMethod(invocation);
}

/// A [UsageProvider] that already holds [plan] (null: not loaded) and never fetches.
UsageProvider usageWith(PlanType? plan) {
  final usage = UsageProvider(subscriptionRequest: () async => plan == null ? null : subscriptionOn(plan));
  if (plan != null) usage.debugSetSubscription(subscriptionOn(plan));
  return usage;
}

Widget chatAppsHost(
  Widget home, {
  required MessagingChannelsProvider provider,
  UsageProvider? usage,
  ConnectivityProvider? connectivity,
  Brightness brightness = Brightness.dark,
}) {
  OmiColors.active = OmiColors.forBrightness(brightness);
  return MultiProvider(
    providers: [
      ChangeNotifierProvider<MessagingChannelsProvider>.value(value: provider),
      ChangeNotifierProvider<UsageProvider>.value(value: usage ?? usageWith(PlanType.architect)),
      ChangeNotifierProvider<ConnectivityProvider>.value(value: connectivity ?? StubConnectivity()),
    ],
    child: MaterialApp(
      theme: buildOmiTheme(brightness: brightness),
      localizationsDelegates: AppLocalizations.localizationsDelegates,
      supportedLocales: AppLocalizations.supportedLocales,
      home: home,
    ),
  );
}

/// Lets the fake backend's futures complete and the frame settle.
Future<void> settle(WidgetTester tester) async {
  for (var i = 0; i < 5; i++) {
    await tester.pump(const Duration(milliseconds: 50));
  }
}

/// The audit's phone size, 390x844.
void usePhoneViewport(WidgetTester tester) {
  tester.view.physicalSize = const Size(390, 844);
  tester.view.devicePixelRatio = 1;
  addTearDown(tester.view.reset);
}
