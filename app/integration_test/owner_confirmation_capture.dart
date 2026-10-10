// Native, loopback-only acceptance target. Uses the real card, player, provider,
// transcript widget and segment reconciliation with synthetic backend storage.
import 'dart:convert';
import 'dart:io';
import 'dart:typed_data';

import 'package:flutter/material.dart';
import 'package:audio_session/audio_session.dart';
import 'package:marionette_flutter/marionette_flutter.dart';
import 'package:provider/provider.dart';
import 'package:omi/backend/http/api_result.dart';
import 'package:omi/backend/schema/conversation.dart';
import 'package:omi/backend/schema/gen/speaker_tag_prompts_wire.g.dart';
import 'package:omi/backend/schema/structured.dart';
import 'package:omi/backend/schema/transcript_segment.dart';
import 'package:omi/l10n/app_localizations.dart';
import 'package:omi/pages/conversations/widgets/speaker_tag_prompt_card.dart';
import 'package:omi/providers/conversation_provider.dart';
import 'package:omi/providers/people_provider.dart';
import 'package:omi/backend/http/api/users.dart';
import 'package:omi/providers/speaker_tag_prompts_provider.dart';
import 'package:omi/ui/ui.dart';
import 'package:omi/widgets/transcript.dart';

const _base = String.fromEnvironment('OWNER_CONFIRMATION_FIXTURE_URL', defaultValue: 'http://127.0.0.1:18955');

Future<dynamic> _request(String path, {Map<String, dynamic>? body}) async {
  final client = HttpClient();
  try {
    final uri = Uri.parse('$_base$path');
    final request = body == null ? await client.getUrl(uri) : await client.postUrl(uri);
    if (body != null) {
      request.headers.contentType = ContentType.json;
      request.write(jsonEncode(body));
    }
    final response = await request.close();
    final text = await utf8.decoder.bind(response).join();
    if (response.statusCode != 200) throw HttpException('${response.statusCode}: $text');
    return jsonDecode(text);
  } finally {
    client.close();
  }
}

Future<void> main() async {
  MarionetteBinding.ensureInitialized();
  final audioSession = await AudioSession.instance;
  await audioSession.configure(const AudioSessionConfiguration.speech());
  OmiColors.active = OmiColors.forBrightness(Brightness.dark);
  runApp(const _Capture());
}

class _Capture extends StatefulWidget {
  const _Capture();
  @override
  State<_Capture> createState() => _CaptureState();
}

class _CaptureState extends State<_Capture> {
  final conversation = ConversationProvider(isSignedIn: () => false);
  final people = PeopleProvider(loadPeople: () async => const PeopleListResponse(people: []));
  late final SpeakerTagPromptsProvider prompts;
  ServerConversation? row;

  @override
  void initState() {
    super.initState();
    prompts = SpeakerTagPromptsProvider(
      fetchPrompts: () async => ApiSuccess(GeneratedSpeakerTagPromptsResponse.fromJson(
          await _request('/v1/speaker-tag-prompts?owner_excerpt=true') as Map<String, dynamic>)),
      markShown: (ids, {bool setShown = true}) async {
        await _request('/v1/speaker-tag-prompts/shown', body: {'prompt_ids': ids, 'set_shown': setShown});
        return const ApiSuccess(false);
      },
      loadClip: (prompt) async {
        final query = Uri(queryParameters: {
          'conversation_id': prompt.conversationId,
          'start': '${prompt.clipStart}',
          'end': '${prompt.clipEnd}',
          'prompt_id': prompt.id,
          'evidence_id': prompt.evidenceId
        }).query;
        final clip = await _request('/v1/speaker-tag-prompts/clip?$query');
        return ApiSuccess(Uint8List.fromList(base64Decode(clip['audio_base64'] as String)));
      },
      submitAnswer: (request) async => ApiSuccess(GeneratedSpeakerTagPromptAnswerResponse.fromJson(
          await _request('/v1/speaker-tag-prompts/answer', body: request.toJson()) as Map<String, dynamic>)),
      emit: (_) {},
      answeredHold: const Duration(seconds: 4),
    );
    _load();
  }

  Future<void> _load() async {
    final segments = (await _request('/fixture/transcript') as List)
        .map((s) => TranscriptSegment.fromJson(s as Map<String, dynamic>))
        .toList();
    row = ServerConversation(
        id: 'synthetic-conversation',
        createdAt: DateTime.now(),
        structured: Structured('Synthetic coffee chat', ''),
        transcriptSegments: segments);
    conversation.conversations = [row!];
    if (mounted) setState(() {});
  }

  Future<void> _reset(bool owner) async {
    await _request('/fixture/reset?owner=$owner', body: {});
    prompts.clearUserData();
    await _load();
    await prompts.loadIfDue(force: true);
  }

  @override
  void dispose() {
    prompts.dispose();
    conversation.dispose();
    people.dispose();
    super.dispose();
  }

  @override
  Widget build(BuildContext context) => MultiProvider(
        providers: [
          ChangeNotifierProvider.value(value: people),
          ChangeNotifierProvider.value(value: prompts),
          ChangeNotifierProvider.value(value: conversation)
        ],
        child: MaterialApp(
          debugShowCheckedModeBanner: false,
          theme: buildOmiTheme(brightness: Brightness.dark),
          localizationsDelegates: AppLocalizations.localizationsDelegates,
          supportedLocales: const [Locale('en')],
          home: Scaffold(
            appBar: AppBar(title: const Text('Synthetic owner confirmation')),
            body: row == null
                ? const Center(child: OmiSpinner())
                : Column(children: [
                    const SpeakerTagPromptCard(),
                    Expanded(
                        child: Consumer<ConversationProvider>(
                            builder: (context, provider, _) => TranscriptWidget(
                                  key: ValueKey(prompts.answeredCount),
                                  segments: row!.transcriptSegments,
                                  bottomMargin: 16,
                                  contentVersion: prompts.answeredCount,
                                ))),
                    Row(mainAxisAlignment: MainAxisAlignment.center, children: [
                      TextButton(
                          key: const Key('fixture_reset'),
                          onPressed: () => _reset(false),
                          child: const Text('Reset unknown excerpt')),
                      TextButton(
                          key: const Key('fixture_reset_owner'),
                          onPressed: () => _reset(true),
                          child: const Text('Reset owner excerpt')),
                    ]),
                  ]),
          ),
        ),
      );
}
