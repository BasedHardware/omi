import 'package:flutter/material.dart';
import 'package:omi/backend/http/api_result.dart';
import 'package:omi/backend/preferences.dart';
import 'package:omi/backend/schema/bt_device/bt_device.dart';
import 'package:omi/backend/schema/folder.dart';
import 'package:omi/backend/schema/gen/speaker_tag_prompts_wire.g.dart';
import 'package:omi/backend/schema/phone_call.dart';
import 'package:omi/l10n/app_localizations.dart';
import 'package:omi/models/local_recording.dart';
import 'package:omi/pages/conversations/conversations_page.dart';
import 'package:omi/providers/capture_provider.dart';
import 'package:omi/providers/conversation_provider.dart';
import 'package:omi/providers/device_provider.dart';
import 'package:omi/providers/folder_provider.dart';
import 'package:omi/providers/home_provider.dart';
import 'package:omi/providers/local_recordings_provider.dart';
import 'package:omi/providers/phone_call_provider.dart';
import 'package:omi/providers/speaker_tag_prompts_provider.dart';
import 'package:omi/services/capture/capture_external_actions.dart';
import 'package:omi/services/capture/local_segment_store.dart';
import 'package:provider/provider.dart';
import 'package:shared_preferences/shared_preferences.dart';

class _InertLocalRecordingsProvider extends ChangeNotifier implements LocalRecordingsProvider {
  @override
  List<LocalRecording> get recordings => const [];

  @override
  Future<void> refresh() async {}

  @override
  dynamic noSuchMethod(Invocation invocation) => super.noSuchMethod(invocation);
}

class _InertDeviceProvider extends ChangeNotifier implements DeviceProvider {
  @override
  bool get havingNewFirmware => false;

  @override
  BtDevice? get pairedDevice => null;

  @override
  bool get isConnected => false;

  @override
  dynamic noSuchMethod(Invocation invocation) => super.noSuchMethod(invocation);
}

class _InertPhoneCallProvider extends ChangeNotifier implements PhoneCallProvider {
  @override
  PhoneCallState get callState => PhoneCallState.idle;

  @override
  dynamic noSuchMethod(Invocation invocation) => super.noSuchMethod(invocation);
}

/// Builder-owned fixture composition only: supply inert explicit collaborators
/// around the real ConversationsPage and this exact real provider. Never replace
/// its build method, use an offstage decoy, or construct default CaptureProvider.
/// Include real MaterialApp localization delegates. Spine tests check actual page
/// ancestry and behavior; fixture wiring is deliberately editable by the builder.
Future<Widget> buildTypedConversationScreen(ConversationProvider provider) async {
  SharedPreferences.setMockInitialValues({});
  await SharedPreferencesUtil.init();
  SharedPreferencesUtil().showGoalTrackerEnabled = false;

  final recordings = _InertLocalRecordingsProvider();
  final folders = FolderProvider(foldersFetcher: () async => <Folder>[]);
  final home = HomeProvider();
  final device = _InertDeviceProvider();
  final phone = _InertPhoneCallProvider();
  // No speaker tag prompts: the fetch seam returns an empty set, so the card stays hidden and does no I/O.
  final speakerTagPrompts = SpeakerTagPromptsProvider(
    fetchPrompts: () async => const ApiSuccess(GeneratedSpeakerTagPromptsResponse()),
  );
  final capture = CaptureProvider(
    externalActions: const NoopCaptureExternalActions(),
    inProgressConversationLoader: () async {},
    localSegmentStore: LocalSegmentStore.disabled(),
  );

  return MaterialApp(
    localizationsDelegates: AppLocalizations.localizationsDelegates,
    supportedLocales: const [Locale('en')],
    home: MultiProvider(
      providers: [
        ChangeNotifierProvider<ConversationProvider>.value(value: provider),
        ChangeNotifierProvider<LocalRecordingsProvider>.value(value: recordings),
        ChangeNotifierProvider<FolderProvider>.value(value: folders),
        ChangeNotifierProvider<HomeProvider>.value(value: home),
        ChangeNotifierProvider<DeviceProvider>.value(value: device),
        ChangeNotifierProvider<PhoneCallProvider>.value(value: phone),
        ChangeNotifierProvider<CaptureProvider>.value(value: capture),
        ChangeNotifierProvider<SpeakerTagPromptsProvider>.value(value: speakerTagPrompts),
      ],
      child: const Scaffold(body: ConversationsPage(requestInitialLoad: false)),
    ),
  );
}
