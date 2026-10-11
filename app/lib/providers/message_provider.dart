import 'dart:async';
import 'dart:convert';
import 'dart:io';

import 'package:omi/utils/platform/platform_manager.dart';
import 'package:flutter/foundation.dart';
import 'package:flutter/material.dart';
import 'package:flutter/services.dart';

import 'package:collection/collection.dart';
import 'package:file_picker/file_picker.dart';
import 'package:http/http.dart' as http;
import 'package:image_picker/image_picker.dart';
import 'package:path/path.dart' as p;
import 'package:uuid/uuid.dart';

import 'package:omi/backend/http/api/apps.dart';
import 'package:omi/backend/http/api/messages.dart';
import 'package:omi/backend/http/api/users.dart';
import 'package:omi/backend/http/api_result.dart';
import 'package:omi/backend/http/streaming_error.dart';
import 'package:omi/services/app_review_service.dart';
import 'package:omi/services/voice_playback/chat_reply_read_aloud.dart';
import 'package:omi/services/voice_playback/omi_voice_playback_service.dart';
import 'package:omi/utils/analytics/registry/events.g.dart';
import 'package:omi/utils/analytics/registry/typed_events.dart';
import 'package:omi/backend/schema/app.dart';
import 'package:omi/backend/schema/bt_device/bt_device.dart';
import 'package:omi/backend/schema/gen/apps_wire.g.dart' as wire;
import 'package:omi/backend/schema/message.dart';
import 'package:omi/providers/app_provider.dart';
import 'package:omi/providers/chat_history_state.dart';
import 'package:omi/backend/http/api/chat_sessions.dart';
import 'package:omi/app_globals.dart';
import 'package:omi/utils/alerts/app_snackbar.dart';
import 'package:omi/utils/l10n_extensions.dart';
import 'package:omi/utils/file.dart';
import 'package:omi/utils/logger.dart';
import 'package:omi/utils/analytics/product_telemetry.dart';

typedef ChatFilesUploader = Future<List<MessageFile>?> Function(List<File> files, {String? appId});
typedef ChatReplyStreamer = Stream<ServerMessageChunk> Function(
  String text, {
  String? appId,
  List<String>? filesId,
  ChatPageContext? context,
  String? chatSessionId,
});
typedef VoiceReplyStreamer = Stream<ServerMessageChunk> Function(List<File> files, {String? language});
typedef VoiceAudioFileSaver = Future<File> Function(List<List<int>> bytes, int startTime, int frameSize);

class _ChatTelemetryAttempt {
  _ChatTelemetryAttempt(this.attempt);

  final ProductAttempt attempt;
  ProductOutcome? outcome;
  ProductFailure failure = ProductFailure.none;
  bool firstResultVisible = false;
  Timer? timeout;

  void dispose() => timeout?.cancel();
}

typedef ChatAppsLoader = Future<ApiResult<wire.GeneratedAppSearchResponse>> Function({int offset, int limit});

/// What to send again when the reader taps Try Again on a failed reply.
class _FailedReply {
  const _FailedReply({this.text, this.context, this.fileIds = const [], this.failure = ChatStreamFailureClass.unknown});

  /// The user's message as it was sent (with any quoted context). Null when the reply cannot be
  /// retried from here (a voice message: its audio is gone).
  final String? text;
  final ChatPageContext? context;
  final List<String> fileIds;

  final ChatStreamFailureClass failure;

  bool get canRetry => text != null;
}

class MessageProvider extends ChangeNotifier with ChatHistoryState {
  MessageProvider({
    ChatFilesUploader? filesUploader,
    ChatSessionsApi? sessionsApi,
    VoiceReplyStreamer? voiceReplyStreamer,
    VoiceAudioFileSaver? voiceAudioFileSaver,
    Duration voiceReplyTimeout = const Duration(seconds: 60),
    ChatReplyReadAloud? readAloud,
  })  : chatSessionsApi = sessionsApi ?? ChatSessionsApi(),
        _filesUploader = filesUploader ?? uploadFilesServer,
        _voiceReplyStreamer = voiceReplyStreamer ?? sendVoiceMessageStreamServer,
        _voiceAudioFileSaver = voiceAudioFileSaver ?? FileUtils.saveAudioBytesToTempFile,
        _voiceReplyTimeout = voiceReplyTimeout,
        _readAloud = readAloud ?? ChatReplyReadAloud.instance;

  @override
  final ChatSessionsApi chatSessionsApi;
  @override
  bool get chatMutationInProgress => sendingMessage || showTypingIndicator || _voiceSendInFlight || isUploadingFiles;
  @override
  void resetChatDraft() {
    _readAloud.revoke();
    _failedReplies.clear();
    clearSelectedFiles();
    clearUploadedFiles();
  }

  final ChatFilesUploader _filesUploader;
  final VoiceReplyStreamer _voiceReplyStreamer;
  final VoiceAudioFileSaver _voiceAudioFileSaver;
  final Duration _voiceReplyTimeout;
  final ChatReplyReadAloud _readAloud;

  ChatReplyReadAloud get readAloud => _readAloud;

  /// Test seam — replaces [sendMessageStreamServer] for typed messages.
  @visibleForTesting
  ChatReplyStreamer? replyStreamOverride;
  final Map<String, _ChatTelemetryAttempt> _chatTelemetryAttempts = {};

  @override
  AppProvider? appProvider;
  bool _isNextMessageFromVoice = false;

  bool showTypingIndicator = false;
  bool sendingMessage = false;
  double aiStreamProgress = 1.0;
  bool agentThinkingAfterText = false;

  List<App> chatApps = [];
  bool isLoadingChatApps = false;

  ApiProblem? chatAppsProblem;

  @visibleForTesting
  ChatAppsLoader? chatAppsLoaderOverride;

  // Chat quota exceeded — set transiently when backend returns 402
  bool _chatQuotaExceeded = false;
  bool get isChatQuotaExceeded => _chatQuotaExceeded;

  // Replies that failed (network or server error), keyed by the placeholder message object —
  // placeholders share the id '0000', so the id cannot tell two failures apart.
  final Map<ServerMessage, _FailedReply> _failedReplies = Map.identity();

  /// Whether [message] is an AI reply that failed. The chat shows a localized error with Try Again
  /// in its place instead of the raw server text.
  bool isReplyFailed(ServerMessage message) => _failedReplies.containsKey(message);

  /// Whether a failed [message] can be sent again (typed messages can; voice messages cannot).
  bool canRetryReply(ServerMessage message) => _failedReplies[message]?.canRetry ?? false;

  ChatStreamFailureClass? replyFailure(ServerMessage message) => _failedReplies[message]?.failure;

  void _markReplyFailed(ServerMessage message, _FailedReply reply) {
    message.text = '';
    _failedReplies[message] = reply;
  }

  List<File> selectedFiles = [];
  List<String> selectedFileTypes = [];
  List<MessageFile> uploadedFiles = [];
  final Map<File, MessageFile> _uploadedBySelection = Map.identity();
  bool isUploadingFiles = false;
  Map<String, bool> uploadingFiles = {};

  void updateAppProvider(AppProvider p) {
    appProvider = p;
  }

  App? _selectedChatApp() {
    final id = appProvider?.selectedChatAppId;
    if (id != null) {
      for (final app in chatApps) {
        if (app.id == id) return app;
      }
    }
    return appProvider?.getSelectedApp();
  }

  void _registerChatTelemetryAttempt(String messageId, ProductAttempt attempt) {
    _chatTelemetryAttempts[messageId]?.dispose();
    final state = _ChatTelemetryAttempt(attempt);
    _chatTelemetryAttempts[messageId] = state;
    state.timeout = Timer(const Duration(seconds: 30), () {
      if (state.outcome == null || !state.attempt.isComplete) {
        state.attempt.complete(ProductOutcome.unobserved);
      }
      state.dispose();
      _chatTelemetryAttempts.removeWhere((_, candidate) => identical(candidate, state));
    });
  }

  void _transferChatTelemetryAttempt(String oldMessageId, String newMessageId) {
    if (oldMessageId == newMessageId) return;
    final state = _chatTelemetryAttempts.remove(oldMessageId);
    if (state == null) return;
    _chatTelemetryAttempts[newMessageId]?.dispose();
    _chatTelemetryAttempts[newMessageId] = state;
  }

  void _finishChatTelemetryAttempt(
    String messageId,
    ProductOutcome outcome, {
    ProductFailure failure = ProductFailure.none,
  }) {
    final state = _chatTelemetryAttempts[messageId];
    if (state == null) return;
    state.outcome = outcome;
    state.failure = failure;
    if (outcome != ProductOutcome.success || state.firstResultVisible) {
      state.attempt.complete(outcome, failure: failure);
      state.dispose();
      _chatTelemetryAttempts.remove(messageId);
    }
  }

  /// Called by the AI message widget after its content has been laid out.
  /// Transport completion alone never counts as a first visible answer.
  void markChatResultVisible(String messageId) {
    final state = _chatTelemetryAttempts[messageId];
    if (state == null || state.firstResultVisible || state.attempt.isComplete) return;
    state.firstResultVisible = true;
    state.attempt.firstResult();
    if (state.outcome != null) {
      state.attempt.complete(state.outcome!, failure: state.failure);
      state.dispose();
      _chatTelemetryAttempts.remove(messageId);
    }
  }

  void setChatApps(List<App> apps) {
    chatApps = apps;
    notifyListeners();
  }

  void removeChatApp(String appId) {
    chatApps.removeWhere((app) => app.id == appId);
    notifyListeners();
  }

  Future<void> fetchChatApps() async {
    if (isLoadingChatApps) return;

    isLoadingChatApps = true;
    notifyListeners();

    try {
      final loader = chatAppsLoaderOverride ?? retrieveInstalledChatApps;
      final apps = <App>[];
      const limit = 100;
      var offset = 0;
      while (true) {
        final result = await loader(offset: offset, limit: limit);
        if (result is ApiFailure<wire.GeneratedAppSearchResponse>) {
          chatAppsProblem = result.problem;
          Logger.warning(
            'mobile_chat_failure class=${result.problem.kind} stage=chatAppsFetch status=${result.problem.statusCode}',
          );
          return;
        }
        final page = (result as ApiSuccess<wire.GeneratedAppSearchResponse>).data;
        apps.addAll(
          (page.data ?? const <wire.GeneratedAppCatalogItem>[])
              .map(App.fromGeneratedCatalogItem)
              .where((app) => !app.deleted),
        );
        if (!page.pagination.hasNext) break;
        offset += limit;
      }
      chatApps = apps.where((app) => app.worksWithChat()).toList();
      chatAppsProblem = null;
    } catch (e) {
      Logger.debug('Error fetching chat apps: $e');
      chatAppsProblem = ApiProblem(
        e is TimeoutException || e is SocketException || e is http.ClientException
            ? ApiProblemKind.transport
            : ApiProblemKind.server,
      );
    } finally {
      isLoadingChatApps = false;
      notifyListeners();
    }
  }

  void setNextMessageOriginIsVoice(bool isVoice) {
    _isNextMessageFromVoice = isVoice;
  }

  void setIsUploadingFiles() {
    if (uploadingFiles.values.contains(true)) {
      isUploadingFiles = true;
    } else {
      isUploadingFiles = false;
    }
    notifyListeners();
  }

  void setMultiUploadingFileStatus(List<String> ids, bool value) {
    for (var id in ids) {
      uploadingFiles[id] = value;
    }
    setIsUploadingFiles();
    notifyListeners();
  }

  Future<void> addFiles(List<File> files) async {
    if (selectedFiles.length + files.length > 4) {
      AppSnackbar.showSnackbarError('You can only select up to 4 files');
      return;
    }

    List<File> filesToAdd = [];
    List<String> typesToAdd = [];

    for (var file in files) {
      String ext = p.extension(file.path).toLowerCase().replaceAll('.', '');
      if (['jpg', 'jpeg', 'png', 'gif', 'bmp', 'webp', 'heic', 'tiff', 'tif'].contains(ext)) {
        typesToAdd.add('image');
      } else {
        typesToAdd.add('file');
      }
      filesToAdd.add(file);
    }

    if (filesToAdd.isNotEmpty) {
      selectedFiles.addAll(filesToAdd);
      selectedFileTypes.addAll(typesToAdd);
      try {
        await uploadFiles(filesToAdd, appProvider?.selectedChatAppId);
      } catch (e) {
        Logger.debug('Failed to upload files: $e');
        if (selectedFiles.length >= filesToAdd.length) {
          selectedFiles.removeRange(selectedFiles.length - filesToAdd.length, selectedFiles.length);
          selectedFileTypes.removeRange(selectedFileTypes.length - filesToAdd.length, selectedFileTypes.length);
        }
        AppSnackbar.showSnackbarError('File upload failed. Please try again.');
      }
      notifyListeners();
    }
  }

  bool isFileUploading(String id) {
    return uploadingFiles[id] ?? false;
  }

  void setSendingMessage(bool value) {
    sendingMessage = value;
    notifyListeners();
  }

  void setShowTypingIndicator(bool value) {
    showTypingIndicator = value;
    notifyListeners();
  }

  void captureImage() async {
    final l10n = globalNavigatorKey.currentContext?.l10n;
    try {
      var res = await ImagePicker().pickImage(source: ImageSource.camera);
      if (res != null) {
        selectedFiles.add(File(res.path));
        selectedFileTypes.add('image');
        var index = selectedFiles.length - 1;
        await uploadFiles([selectedFiles[index]], appProvider?.selectedChatAppId);
        notifyListeners();
      }
    } on PlatformException catch (e) {
      if (e.code == 'camera_access_denied') {
        AppSnackbar.showSnackbarError(
          l10n?.msgCameraPermissionDenied ?? 'Camera permission denied. Please allow access to camera',
        );
      } else {
        AppSnackbar.showSnackbarError(
          l10n?.msgCameraAccessError(e.message ?? e.code) ?? 'Error accessing camera: ${e.message ?? e.code}',
        );
      }
    } catch (e) {
      AppSnackbar.showSnackbarError(l10n?.msgPhotoError ?? 'Error taking photo. Please try again.');
    }
  }

  void selectImage() async {
    final l10n = globalNavigatorKey.currentContext?.l10n;
    if (selectedFiles.length >= 4) {
      AppSnackbar.showSnackbarError(l10n?.msgMaxImagesLimit ?? 'You can only select up to 4 images');
      return;
    }

    try {
      List<File> files = [];

      List res = [];
      if (4 - selectedFiles.length == 1) {
        var image = await ImagePicker().pickImage(source: ImageSource.gallery);
        if (image != null) {
          res = [image];
        }
      } else {
        res = await ImagePicker().pickMultiImage(limit: 4 - selectedFiles.length);
      }

      for (var r in res) {
        files.add(File(r.path));
      }

      if (files.isNotEmpty) {
        selectedFiles.addAll(files);
        selectedFileTypes.addAll(files.map((e) => 'image'));
        await uploadFiles(files, appProvider?.selectedChatAppId);
      }
      notifyListeners();
    } on PlatformException catch (e) {
      Logger.debug('🖼️ PlatformException during image picking: ${e.code} - ${e.message}');
      if (e.code == 'photo_access_denied') {
        AppSnackbar.showSnackbarError(
          l10n?.msgPhotosPermissionDenied ?? 'Photos permission denied. Please allow access to photos to select images',
        );
      } else {
        AppSnackbar.showSnackbarError(
          l10n?.msgSelectImagesError(e.message ?? e.code) ?? 'Error selecting images: ${e.message ?? e.code}',
        );
      }
    } catch (e) {
      Logger.debug('🖼️ General exception during image picking: $e');
      AppSnackbar.showSnackbarError(l10n?.msgSelectImagesGenericError ?? 'Error selecting images. Please try again.');
    }
  }

  void selectFile() async {
    final l10n = globalNavigatorKey.currentContext?.l10n;
    if (selectedFiles.length >= 4) {
      AppSnackbar.showSnackbarError(l10n?.msgMaxFilesLimit ?? 'You can only select up to 4 files');
      return;
    }

    try {
      var res = await FilePicker.platform.pickFiles(
        type: FileType.custom,
        allowMultiple: true,
        allowedExtensions: ['jpeg', 'md', 'pdf', 'gif', 'doc', 'png', 'pptx', 'txt', 'xlsx', 'webp'],
        dialogTitle: l10n?.chooseFile ?? 'Select files',
        withData: false,
        withReadStream: false,
      );

      if (res != null && res.files.isNotEmpty) {
        List<File> files = [];
        for (var r in res.files) {
          if (r.path != null && files.length < (4 - selectedFiles.length)) {
            files.add(File(r.path!));
          }
        }

        if (files.isNotEmpty) {
          selectedFiles.addAll(files);
          selectedFileTypes.addAll(files.map((e) => 'file'));
          await uploadFiles(files, appProvider?.selectedChatAppId);
        }
        notifyListeners();
      }
    } on PlatformException catch (e) {
      AppSnackbar.showSnackbarError(
        l10n?.msgSelectFilesError(e.message ?? e.code) ?? 'Error selecting files: ${e.message ?? e.code}',
      );
    } catch (e) {
      AppSnackbar.showSnackbarError(l10n?.msgSelectFilesGenericError ?? 'Error selecting files. Please try again.');
    }
  }

  void clearSelectedFile(int index) {
    if (index < 0 || index >= selectedFiles.length) return;
    final removed = selectedFiles.removeAt(index);
    selectedFileTypes.removeAt(index);
    final uploaded = _uploadedBySelection.remove(removed);
    if (uploaded != null) uploadedFiles.remove(uploaded);
    notifyListeners();
  }

  void clearSelectedFiles() {
    selectedFiles.clear();
    selectedFileTypes.clear();
    _uploadedBySelection.clear();
    notifyListeners();
  }

  void clearUploadedFiles() {
    uploadedFiles.clear();
    _uploadedBySelection.clear();
    notifyListeners();
  }

  void clearUserData() {
    _readAloud.revoke();
    messages = [];
    chatApps = [];
    selectedFiles = [];
    selectedFileTypes = [];
    uploadedFiles = [];
    _uploadedBySelection.clear();
    uploadingFiles = {};
    notifyListeners();
  }

  Future<List<MessageFile>?> uploadFiles(List<File> files, String? appId) async {
    if (files.isNotEmpty) {
      setMultiUploadingFileStatus(files.map((e) => e.path).toList(), true);
      List<MessageFile>? res;
      try {
        res = await _filesUploader(files, appId: appId);
      } catch (e) {
        Logger.debug('uploadFiles failed: $e');
        res = null;
      }
      if (res != null) {
        for (var i = 0; i < res.length && i < files.length; i++) {
          if (!selectedFiles.any((f) => identical(f, files[i]))) continue;
          uploadedFiles.add(res[i]);
          _uploadedBySelection[files[i]] = res[i];
        }
      } else {
        for (var i = selectedFiles.length - 1; i >= 0; i--) {
          if (files.any((f) => identical(f, selectedFiles[i]))) {
            selectedFiles.removeAt(i);
            selectedFileTypes.removeAt(i);
          }
        }
        final l10n = globalNavigatorKey.currentContext?.l10n;
        AppSnackbar.showSnackbarError(l10n?.msgUploadFileFailed ?? 'Failed to upload file, please try again later');
      }
      setMultiUploadingFileStatus(files.map((e) => e.path).toList(), false);
      notifyListeners();
      return res;
    }

    return null;
  }

  void removeLocalMessage(String id) {
    messages.removeWhere((m) => m.id == id);
    notifyListeners();
  }

  Future<bool> setMessageNps(ServerMessage message, int value, {String? reason}) async {
    if (!await setMessageResponseRating(message.id, value, reason: reason)) return false;
    if (value == -1) unawaited(AppReviewService().recordBadExperience(AppReviewBadExperience.negativeChatRating));
    message.askForNps = false;
    // Update local message rating so it persists when scrolling
    message.rating = value == 0 ? null : value;
    notifyListeners();
    return true;
  }

  void addMessageLocally(String messageText) {
    List<String> fileIds = uploadedFiles.map((e) => e.id).toList();
    var appId = appProvider?.selectedChatAppId;
    if (appId == 'no_selected') {
      appId = null;
    }
    // Use local file paths as thumbnails so images display immediately
    List<MessageFile> localFiles = List.from(uploadedFiles);
    for (int i = 0; i < localFiles.length && i < selectedFiles.length; i++) {
      if (localFiles[i].mimeTypeToFileType() == 'image') {
        localFiles[i].thumbnail = selectedFiles[i].path;
      }
    }
    var message = ServerMessage(
      const Uuid().v4(),
      DateTime.now(),
      messageText,
      MessageSender.human,
      MessageType.text,
      appId,
      false,
      localFiles,
      fileIds,
      [],
    );
    if (messages.firstWhereOrNull((m) => m.id == message.id) != null) {
      return;
    }
    messages.add(message);
    notifyListeners();
  }

  void addMessage(ServerMessage message) {
    if (message.isAutomaticChatEntry) return;
    if (messages.firstWhereOrNull((m) => m.id == message.id) != null) {
      return;
    }
    messages.add(message);
    notifyListeners();
  }

  bool _voiceSendInFlight = false;

  void _recordPendantVoiceQuestionDrop(PendantVoiceQuestionDroppedReason reason) {
    Logger.warning('Pendant voice question dropped: ${reason.wireName}');
    const TypedEvents().emit(PendantVoiceQuestionDropped(reason: reason));
  }

  Future sendVoiceMessageStreamToServer(
    List<List<int>> audioBytes, {
    Function? onFirstChunkRecived,
    Future<void> Function()? onNoSpeech,
    BleAudioCodec? codec,
    bool playResponseAudio = false,
  }) async {
    // Re-entry guard so a duplicated end-of-session signal from the device
    // button can't kick off two parallel voice replies.
    if (_voiceSendInFlight || sendingMessage || showTypingIndicator) {
      _recordPendantVoiceQuestionDrop(PendantVoiceQuestionDroppedReason.sendInFlight);
      return;
    }
    if (audioBytes.isEmpty) {
      _recordPendantVoiceQuestionDrop(PendantVoiceQuestionDroppedReason.emptyFrames);
      return;
    }
    _voiceSendInFlight = true;
    _readAloud.newQuery();
    final readAloudGeneration = _readAloud.generation;
    var readAloudDelivered = false;
    // Pendant voice addresses the server-current conversation. Its playback may continue while
    // Past chats is open, but its transient reply must never become a row in an archived thread.
    final voiceMessages = chatSessionId == null && !isFreshChat ? messages : <ServerMessage>[];
    final visibleVoice = identical(voiceMessages, messages);
    final chatAttempt = ProductTelemetry.instance.start(ProductJourney.chatVoice, surface: ProductSurface.chat);
    var chatAttemptCompleted = false;
    late String responseMessageId;
    void completeChat(ProductOutcome outcome, {ProductFailure failure = ProductFailure.none}) {
      if (chatAttemptCompleted) return;
      chatAttemptCompleted = true;
      _finishChatTelemetryAttempt(responseMessageId, outcome, failure: failure);
    }

    _chatQuotaExceeded = false; // Clear stale quota state from previous sends
    late final File file;
    try {
      file = await _voiceAudioFileSaver(
        audioBytes,
        DateTime.now().millisecondsSinceEpoch ~/ 1000 - (audioBytes.length / 100).ceil(),
        codec?.getFrameSize() ?? 160,
      );
    } catch (_) {
      _voiceSendInFlight = false;
      _recordPendantVoiceQuestionDrop(PendantVoiceQuestionDroppedReason.audioSaveFailed);
      chatAttempt.complete(ProductOutcome.failure, failure: ProductFailure.unknown);
      return;
    }

    var currentAppId = appProvider?.selectedChatAppId;
    if (currentAppId == 'no_selected') {
      currentAppId = null;
    }
    String chatTargetId = currentAppId ?? 'omi';
    // The voice endpoint has no app field and the backend voice pipeline runs
    // without an app persona (`app = None`), so a voice turn never uses the
    // selected app's persona even when one is picked. Reporting it as persona
    // chat would overcount; only the typed path honors the selection today.
    const bool isPersonaChat = false;

    PlatformManager.instance.analytics.chatVoiceInputUsed(chatTargetId: chatTargetId, isPersonaChat: isPersonaChat);

    if (visibleVoice) setShowTypingIndicator(true);
    var message = ServerMessage.empty();
    voiceMessages.add(message);
    var aiIndex = voiceMessages.length - 1;
    responseMessageId = message.id;
    _registerChatTelemetryAttempt(responseMessageId, chatAttempt);
    notifyListeners();

    // Voice response playback is triggered only from the Omi device-button
    // path (capture_provider). The chat-screen mic input does not pass
    // playResponseAudio=true.
    final String playbackMessageId = message.id;
    try {
      if (playResponseAudio) {
        await OmiVoicePlaybackService.instance.beginResponse(messageId: playbackMessageId);
      }
      bool firstChunkRecieved = false;
      await for (var chunk in _voiceReplyStreamer([file]).timeout(_voiceReplyTimeout)) {
        if (!firstChunkRecieved &&
            [
              MessageChunkType.message,
              MessageChunkType.data,
              MessageChunkType.done,
              MessageChunkType.think,
            ].contains(chunk.type)) {
          firstChunkRecieved = true;
          if (onFirstChunkRecived != null) {
            onFirstChunkRecived();
          }
        }

        if (chunk.type == MessageChunkType.think) {
          message.thinkings.add(chunk.text);
          notifyListeners();
          continue;
        }

        if (chunk.type == MessageChunkType.memory) {
          message.memoryAction = chunk.text;
          notifyListeners();
          continue;
        }

        if (chunk.type == MessageChunkType.data) {
          message.text += chunk.text;
          if (playResponseAudio) {
            OmiVoicePlaybackService.instance.updateStreamingResponse(
              messageId: playbackMessageId,
              fullText: message.text,
              isFinal: false,
            );
          }
          notifyListeners();
          continue;
        }

        if (chunk.type == MessageChunkType.done) {
          chunk.message!.memoryAction = message.memoryAction;
          message = chunk.message!;
          voiceMessages[aiIndex] = message;
          _transferChatTelemetryAttempt(responseMessageId, message.id);
          _finishChatTelemetryAttempt(message.id, ProductOutcome.success);
          chatAttemptCompleted = true;
          if (playResponseAudio) {
            OmiVoicePlaybackService.instance.updateStreamingResponse(
              messageId: playbackMessageId,
              fullText: message.text,
              isFinal: true,
            );
          } else if (!readAloudDelivered) {
            readAloudDelivered = true;
            unawaited(_readAloud.readFinalReply(message.text, generation: readAloudGeneration));
          }
          notifyListeners();
          return;
        }

        if (chunk.type == MessageChunkType.message) {
          voiceMessages.insert(aiIndex, chunk.message!);
          aiIndex++;
          notifyListeners();
          continue;
        }

        if (chunk.type == MessageChunkType.error) {
          if (chunk.errorCode == 'no_speech') {
            final l10n = globalNavigatorKey.currentContext?.l10n;
            message.text = l10n?.voiceQuestionNoSpeech ?? "Didn't catch that — try again";
            if (playResponseAudio) {
              await OmiVoicePlaybackService.instance.interrupt(source: VoiceReplyPlaybackInterruptSource.streamError);
            }
            if (onNoSpeech != null) await onNoSpeech();
            completeChat(ProductOutcome.empty);
            notifyListeners();
            return;
          }
          if (chunk.errorCode == 'quota_exceeded' || _tryParseQuotaError(chunk.text)) {
            _chatQuotaExceeded = true;
            final l10n = globalNavigatorKey.currentContext?.l10n;
            message.text = l10n?.chatQuotaExceededReply ??
                "You've hit your monthly limit. Upgrade to keep chatting with Omi without restrictions.";
            if (playResponseAudio) {
              await OmiVoicePlaybackService.instance.interrupt(source: VoiceReplyPlaybackInterruptSource.quotaError);
            }
            notifyListeners();
            setShowTypingIndicator(false);
            _logChatFailure(ChatStreamFailureClass.quota, stage: 'voice_stream');
            completeChat(ProductOutcome.failure, failure: ProductFailure.quota);
            return;
          }
          final failure = _chunkFailureClass(chunk);
          _logChatFailure(failure, stage: 'voice_stream');
          _markReplyFailed(message, _FailedReply(failure: failure));
          if (playResponseAudio) {
            await OmiVoicePlaybackService.instance.interrupt(source: VoiceReplyPlaybackInterruptSource.streamError);
          }
          completeChat(ProductOutcome.failure, failure: _productFailureFor(failure));
          notifyListeners();
          return;
        }
      }
    } catch (e) {
      final failure = classifyChatStreamFailure(e);
      _logChatFailure(failure.kind, stage: 'voice_transport', status: failure.statusCode);
      _markReplyFailed(message, _FailedReply(failure: failure.kind));
      if (playResponseAudio) {
        await OmiVoicePlaybackService.instance.interrupt(source: VoiceReplyPlaybackInterruptSource.streamError);
      }
      completeChat(ProductOutcome.failure, failure: _productFailureFor(failure.kind));
      notifyListeners();
    } finally {
      _voiceSendInFlight = false;
      setShowTypingIndicator(false);
    }

    if (!chatAttemptCompleted) {
      if (playResponseAudio) {
        await OmiVoicePlaybackService.instance.interrupt(source: VoiceReplyPlaybackInterruptSource.streamError);
      }
      completeChat(ProductOutcome.failure, failure: ProductFailure.incomplete);
    }
  }

  Future sendMessageStreamToServer(String text, {ChatPageContext? context}) => _streamReply(text, context: context);

  /// Streams the reply to [text]. [retryFileIds] resends a failed message's attachments without
  /// touching the files currently selected in the composer (see [retryFailedReply]).
  Future<void> _streamReply(String text, {ChatPageContext? context, List<String>? retryFileIds}) async {
    _chatQuotaExceeded = false; // Clear stale quota state from previous sends
    aiStreamProgress = 0.0;
    beginChatTurn();
    _readAloud.newQuery();
    final readAloudGeneration = _readAloud.generation;
    var readAloudDelivered = false;
    // If Omi was still speaking a prior voice reply, stop it — the user's
    // typed message takes precedence.
    if (OmiVoicePlaybackService.instance.isSpeaking) {
      await OmiVoicePlaybackService.instance.interrupt(source: VoiceReplyPlaybackInterruptSource.userTyped);
    }
    setShowTypingIndicator(true);
    var currentAppId = appProvider?.selectedChatAppId;
    if (currentAppId == 'no_selected') {
      currentAppId = null;
    }

    String chatTargetId = currentAppId ?? 'omi';
    bool isPersonaChat = _selectedChatApp()?.hasCapability('persona') ?? false;

    PlatformManager.instance.analytics.chatMessageSent(
      message: text,
      includesFiles: uploadedFiles.isNotEmpty,
      numberOfFiles: uploadedFiles.length,
      chatTargetId: chatTargetId,
      isPersonaChat: isPersonaChat,
      isVoiceInput: _isNextMessageFromVoice,
    );
    _isNextMessageFromVoice = false;

    final chatAttempt = ProductTelemetry.instance.start(ProductJourney.chatText, surface: ProductSurface.chat);
    var chatAttemptCompleted = false;
    late String responseMessageId;
    void completeChat(ProductOutcome outcome, {ProductFailure failure = ProductFailure.none}) {
      if (chatAttemptCompleted) return;
      chatAttemptCompleted = true;
      _finishChatTelemetryAttempt(responseMessageId, outcome, failure: failure);
    }

    var message = ServerMessage.empty(appId: currentAppId);
    messages.add(message);
    final aiIndex = messages.length - 1;
    responseMessageId = message.id;
    _registerChatTelemetryAttempt(responseMessageId, chatAttempt);
    notifyListeners();
    final List<String> fileIds = retryFileIds ?? uploadedFiles.map((e) => e.id).toList();
    if (retryFileIds == null) {
      clearSelectedFiles();
      clearUploadedFiles();
    }
    String textBuffer = '';
    Timer? timer;

    void flushBuffer() {
      if (textBuffer.isNotEmpty) {
        message.text += textBuffer;
        textBuffer = '';
        aiStreamProgress = (aiStreamProgress + 0.05).clamp(0.0, 1.0);
        HapticFeedback.lightImpact();
        notifyListeners();
      }
    }

    try {
      await prepareChatSession();
      await for (var chunk in (replyStreamOverride ?? sendMessageStreamServer)(
        text,
        appId: currentAppId,
        filesId: fileIds,
        context: context,
        chatSessionId: chatSessionId,
      )) {
        if (chunk.type == MessageChunkType.think) {
          flushBuffer();
          message.thinkings.add(chunk.text);
          if (message.text.isNotEmpty) {
            agentThinkingAfterText = true;
          }
          notifyListeners();
          continue;
        }

        if (chunk.type == MessageChunkType.memory) {
          message.memoryAction = chunk.text;
          notifyListeners();
          continue;
        }

        if (chunk.type == MessageChunkType.data) {
          if (agentThinkingAfterText) {
            agentThinkingAfterText = false;
            notifyListeners();
          }
          textBuffer += chunk.text;
          timer ??= Timer.periodic(const Duration(milliseconds: 100), (_) {
            flushBuffer();
          });
          continue;
        }

        timer?.cancel();
        timer = null;
        flushBuffer();

        if (chunk.type == MessageChunkType.done) {
          chunk.message!.memoryAction = message.memoryAction;
          message = chunk.message!;
          messages[aiIndex] = message;
          _transferChatTelemetryAttempt(responseMessageId, message.id);
          _finishChatTelemetryAttempt(message.id, ProductOutcome.success);
          nameChatSession();
          chatAttemptCompleted = true;
          if (!readAloudDelivered) {
            readAloudDelivered = true;
            unawaited(_readAloud.readFinalReply(message.text, generation: readAloudGeneration));
          }
          notifyListeners();
          return;
        }

        if (chunk.type == MessageChunkType.error) {
          if (chunk.errorCode == 'quota_exceeded' || _tryParseQuotaError(chunk.text)) {
            // Keep the user's message visible; replace AI placeholder with quota message
            _chatQuotaExceeded = true;
            final l10n = globalNavigatorKey.currentContext?.l10n;
            message.text = l10n?.chatQuotaExceededReply ??
                "You've hit your monthly limit. Upgrade to keep chatting with Omi without restrictions.";
            _logChatFailure(ChatStreamFailureClass.quota, stage: 'stream');
            completeChat(ProductOutcome.failure, failure: ProductFailure.quota);
            notifyListeners();
            return;
          }
          final failure = _chunkFailureClass(chunk);
          _logChatFailure(failure, stage: 'stream');
          _markReplyFailed(message, _FailedReply(text: text, context: context, fileIds: fileIds, failure: failure));
          completeChat(ProductOutcome.failure, failure: _productFailureFor(failure));
          notifyListeners();
          return;
        }
      }
    } catch (e) {
      final failure = classifyChatStreamFailure(e);
      _logChatFailure(failure.kind, stage: 'transport', status: failure.statusCode);
      _markReplyFailed(message, _FailedReply(text: text, context: context, fileIds: fileIds, failure: failure.kind));
      completeChat(ProductOutcome.failure, failure: _productFailureFor(failure.kind));
      notifyListeners();
    } finally {
      timer?.cancel();
      flushBuffer();
      aiStreamProgress = 1.0;
      setShowTypingIndicator(false);
      setSendingMessage(false);
    }
    if (!chatAttemptCompleted) {
      _logChatFailure(ChatStreamFailureClass.server, stage: 'eof');
      if (message.text.isEmpty) {
        _markReplyFailed(message,
            _FailedReply(text: text, context: context, fileIds: fileIds, failure: ChatStreamFailureClass.server));
        notifyListeners();
      }
      completeChat(ProductOutcome.failure, failure: ProductFailure.incomplete);
    }
  }

  ChatStreamFailureClass _chunkFailureClass(ServerMessageChunk chunk) => switch (chunk.errorCode) {
        'offline' => ChatStreamFailureClass.offline,
        'server_error' => ChatStreamFailureClass.server,
        'timeout' => ChatStreamFailureClass.timeout,
        'quota_exceeded' => ChatStreamFailureClass.quota,
        'not_signed_in' => ChatStreamFailureClass.notSignedIn,
        _ => ChatStreamFailureClass.server,
      };

  ProductFailure _productFailureFor(ChatStreamFailureClass failure) => switch (failure) {
        ChatStreamFailureClass.offline => ProductFailure.network,
        ChatStreamFailureClass.server => ProductFailure.server,
        ChatStreamFailureClass.timeout => ProductFailure.timeout,
        ChatStreamFailureClass.quota => ProductFailure.quota,
        ChatStreamFailureClass.notSignedIn => ProductFailure.unauthorized,
        ChatStreamFailureClass.unknown => ProductFailure.unknown,
      };

  void _logChatFailure(ChatStreamFailureClass failure, {required String stage, int? status}) {
    Logger.warning('mobile_chat_failure class=${failure.name} stage=$stage status=$status');
  }

  /// Sends the user message behind the failed reply [message] again: the failed reply is removed
  /// and a new one streams in its place. No-op unless [canRetryReply]. The caller owns
  /// [sendingMessage] the same way it does for a normal send.
  Future<void> retryFailedReply(ServerMessage message) async {
    final failed = _failedReplies.remove(message);
    if (failed == null || !failed.canRetry) {
      // The failure was cleared (a refresh) between build and tap: nothing to resend, so release the
      // composer the caller locked.
      setSendingMessage(false);
      return;
    }
    messages.removeWhere((m) => identical(m, message));
    notifyListeners();
    await _streamReply(failed.text!, context: failed.context, retryFileIds: failed.fileIds);
  }

  bool _tryParseQuotaError(String errorText) {
    try {
      var json = jsonDecode(errorText);
      if (json is! Map) return false;
      // FastAPI wraps HTTPException detail in {"detail": {...}}
      var detail = json['detail'] is Map ? json['detail'] as Map<String, dynamic> : json;
      if (detail['error'] == 'quota_exceeded') {
        detail['allowed'] = false;
        _chatQuotaExceeded = true;
        notifyListeners();
        return true;
      }
    } catch (_) {}
    return false;
  }

  Future sendInitialAppMessage(App? app) async {
    setSendingMessage(true);
    try {
      ServerMessage message = await getInitialAppMessage(app?.id);
      addMessage(message);
    } catch (e) {
      Logger.error('sendInitialAppMessage failed: $e');
    } finally {
      setSendingMessage(false);
      notifyListeners();
    }
  }

  App? messageSenderApp(String? appId) {
    return appProvider?.apps.firstWhereOrNull((p) => p.id == appId);
  }

  @override
  void dispose() {
    _readAloud.revoke();
    for (final state in _chatTelemetryAttempts.values) {
      state.dispose();
      if (!state.attempt.isComplete) state.attempt.complete(ProductOutcome.unobserved);
    }
    _chatTelemetryAttempts.clear();
    super.dispose();
  }
}
