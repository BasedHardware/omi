import 'dart:async';
import 'dart:convert';
import 'dart:io';

import 'package:omi/utils/platform/platform_manager.dart';
import 'package:flutter/foundation.dart';
import 'package:flutter/material.dart';
import 'package:flutter/services.dart';

import 'package:collection/collection.dart';
import 'package:file_picker/file_picker.dart';
import 'package:image_picker/image_picker.dart';
import 'package:path/path.dart' as p;
import 'package:uuid/uuid.dart';

import 'package:omi/backend/http/api/apps.dart';
import 'package:omi/backend/http/api/messages.dart';
import 'package:omi/backend/http/api/users.dart';
import 'package:omi/backend/preferences.dart';
import 'package:omi/services/voice_playback/omi_voice_playback_service.dart';
import 'package:omi/backend/schema/app.dart';
import 'package:omi/backend/schema/bt_device/bt_device.dart';
import 'package:omi/backend/schema/message.dart';
import 'package:omi/providers/app_provider.dart';
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
});

class _ChatTelemetryAttempt {
  _ChatTelemetryAttempt(this.attempt);

  final ProductAttempt attempt;
  ProductOutcome? outcome;
  ProductFailure failure = ProductFailure.none;
  bool firstResultVisible = false;
  Timer? timeout;

  void dispose() => timeout?.cancel();
}

/// What to send again when the reader taps Try Again on a failed reply.
class _FailedReply {
  const _FailedReply({this.text, this.context, this.fileIds = const []});

  /// The user's message as it was sent (with any quoted context). Null when the reply cannot be
  /// retried from here (a voice message: its audio is gone).
  final String? text;
  final ChatPageContext? context;
  final List<String> fileIds;

  bool get canRetry => text != null;
}

class MessageProvider extends ChangeNotifier {
  MessageProvider({ChatFilesUploader? filesUploader}) : _filesUploader = filesUploader ?? uploadFilesServer;

  final ChatFilesUploader _filesUploader;

  /// Test seam — replaces [sendMessageStreamServer] for typed messages.
  @visibleForTesting
  ChatReplyStreamer? replyStreamOverride;
  final Map<String, _ChatTelemetryAttempt> _chatTelemetryAttempts = {};

  AppProvider? appProvider;
  List<ServerMessage> messages = [];
  bool _isNextMessageFromVoice = false;

  bool isLoadingMessages = false;
  bool hasCachedMessages = false;
  bool isClearingChat = false;
  bool showTypingIndicator = false;
  bool sendingMessage = false;
  double aiStreamProgress = 1.0;
  bool agentThinkingAfterText = false;

  String firstTimeLoadingText = '';

  List<App> chatApps = [];
  bool isLoadingChatApps = false;

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

  void _finishChatTelemetryAttempt(String messageId, ProductOutcome outcome,
      {ProductFailure failure = ProductFailure.none}) {
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
      final result = await retrieveAppsSearch(installedApps: true, limit: 50);

      chatApps = result.apps.where((app) => app.worksWithChat()).toList();
    } catch (e) {
      Logger.debug('Error fetching chat apps: $e');
      chatApps = [];
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

  void setHasCachedMessages(bool value) {
    hasCachedMessages = value;
    notifyListeners();
  }

  void setSendingMessage(bool value) {
    sendingMessage = value;
    notifyListeners();
  }

  void setShowTypingIndicator(bool value) {
    showTypingIndicator = value;
    notifyListeners();
  }

  void setClearingChat(bool value) {
    isClearingChat = value;
    notifyListeners();
  }

  void setLoadingMessages(bool value) {
    isLoadingMessages = value;
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

  Future refreshMessages({bool dropdownSelected = false}) async {
    _failedReplies.clear();
    setLoadingMessages(true);
    if (SharedPreferencesUtil().cachedMessages.isNotEmpty) {
      setHasCachedMessages(true);
    }
    messages = await getMessagesFromServer(dropdownSelected: dropdownSelected);
    if (messages.isEmpty) {
      messages = List<ServerMessage>.from(SharedPreferencesUtil().cachedMessages);
    } else {
      SharedPreferencesUtil().cachedMessages = messages;
      setHasCachedMessages(true);
    }
    messages.sort((a, b) => a.createdAt.compareTo(b.createdAt));
    setLoadingMessages(false);
    notifyListeners();
  }

  void setMessagesFromCache() {
    if (SharedPreferencesUtil().cachedMessages.isNotEmpty) {
      setHasCachedMessages(true);
      messages = List<ServerMessage>.from(SharedPreferencesUtil().cachedMessages);
      messages.sort((a, b) => a.createdAt.compareTo(b.createdAt));
    }
    notifyListeners();
  }

  Future<List<ServerMessage>> getMessagesFromServer({bool dropdownSelected = false}) async {
    final l10n = globalNavigatorKey.currentContext?.l10n;
    if (!hasCachedMessages) {
      firstTimeLoadingText = l10n?.msgReadingMemories ?? 'Reading your memories…';
      notifyListeners();
    }
    setLoadingMessages(true);
    var mes = await getMessagesServer(appId: appProvider?.selectedChatAppId, dropdownSelected: dropdownSelected);
    if (!hasCachedMessages) {
      firstTimeLoadingText = l10n?.msgLearningMemories ?? 'Learning from your memories…';
      notifyListeners();
    }
    messages = List<ServerMessage>.from(mes);
    messages.sort((a, b) => a.createdAt.compareTo(b.createdAt));
    setLoadingMessages(false);
    notifyListeners();
    return messages;
  }

  Future<bool> setMessageNps(ServerMessage message, int value, {String? reason}) async {
    if (!await setMessageResponseRating(message.id, value, reason: reason)) return false;
    message.askForNps = false;
    // Update local message rating so it persists when scrolling
    message.rating = value == 0 ? null : value;
    notifyListeners();
    return true;
  }

  Future clearChat() async {
    setClearingChat(true);
    try {
      var mes = await clearChatServer(appId: appProvider?.selectedChatAppId);
      _failedReplies.clear();
      messages = List<ServerMessage>.from(mes);
      messages.sort((a, b) => a.createdAt.compareTo(b.createdAt));
    } catch (e) {
      Logger.debug('Failed to clear chat: $e');
      final l10n = globalNavigatorKey.currentContext?.l10n;
      AppSnackbar.showSnackbarError(l10n?.somethingWentWrong ?? 'Something went wrong! Please try again later.');
    } finally {
      setClearingChat(false);
    }
    notifyListeners();
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
    if (messages.firstWhereOrNull((m) => m.id == message.id) != null) {
      return;
    }
    messages.add(message);
    notifyListeners();
  }

  bool _voiceSendInFlight = false;

  Future sendVoiceMessageStreamToServer(
    List<List<int>> audioBytes, {
    Function? onFirstChunkRecived,
    BleAudioCodec? codec,
    bool playResponseAudio = false,
  }) async {
    // Re-entry guard so a duplicated end-of-session signal from the device
    // button can't kick off two parallel voice replies.
    if (_voiceSendInFlight) return;
    if (audioBytes.isEmpty) return;
    _voiceSendInFlight = true;
    final chatAttempt = ProductTelemetry.instance.start(
      ProductJourney.chatVoice,
      surface: ProductSurface.chat,
    );
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
      file = await FileUtils.saveAudioBytesToTempFile(
        audioBytes,
        DateTime.now().millisecondsSinceEpoch ~/ 1000 - (audioBytes.length / 100).ceil(),
        codec?.getFrameSize() ?? 160,
      );
    } catch (_) {
      _voiceSendInFlight = false;
      chatAttempt.complete(ProductOutcome.failure, failure: ProductFailure.unknown);
      return;
    }

    var currentAppId = appProvider?.selectedChatAppId;
    if (currentAppId == 'no_selected') {
      currentAppId = null;
    }
    String chatTargetId = currentAppId ?? 'omi';
    bool isPersonaChat = false;

    PlatformManager.instance.analytics.chatVoiceInputUsed(chatTargetId: chatTargetId, isPersonaChat: isPersonaChat);

    setShowTypingIndicator(true);
    var message = ServerMessage.empty();
    messages.add(message);
    var aiIndex = messages.length - 1;
    responseMessageId = message.id;
    _registerChatTelemetryAttempt(responseMessageId, chatAttempt);
    notifyListeners();

    // Voice response playback is triggered only from the Omi device-button
    // path (capture_provider). The chat-screen mic input does not pass
    // playResponseAudio=true.
    final String playbackMessageId = message.id;
    if (playResponseAudio) {
      await OmiVoicePlaybackService.instance.beginResponse(messageId: playbackMessageId);
    }

    try {
      bool firstChunkRecieved = false;
      await for (var chunk in sendVoiceMessageStreamServer([file])) {
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
          message = chunk.message!;
          messages[aiIndex] = message;
          _transferChatTelemetryAttempt(responseMessageId, message.id);
          _finishChatTelemetryAttempt(message.id, ProductOutcome.success);
          chatAttemptCompleted = true;
          if (playResponseAudio) {
            OmiVoicePlaybackService.instance.updateStreamingResponse(
              messageId: playbackMessageId,
              fullText: message.text,
              isFinal: true,
            );
          }
          notifyListeners();
          continue;
        }

        if (chunk.type == MessageChunkType.message) {
          messages.insert(aiIndex, chunk.message!);
          aiIndex++;
          notifyListeners();
          continue;
        }

        if (chunk.type == MessageChunkType.error) {
          if (_tryParseQuotaError(chunk.text)) {
            final l10n = globalNavigatorKey.currentContext?.l10n;
            message.text = l10n?.chatQuotaExceededReply ??
                "You've hit your monthly limit. Upgrade to keep chatting with Omi without restrictions.";
            if (playResponseAudio) {
              await OmiVoicePlaybackService.instance.interrupt();
            }
            notifyListeners();
            setShowTypingIndicator(false);
            completeChat(ProductOutcome.failure, failure: ProductFailure.quota);
            return;
          }
          Logger.debug('Voice chat reply failed: ${chunk.text}');
          _markReplyFailed(message, const _FailedReply());
          completeChat(ProductOutcome.failure, failure: ProductFailure.server);
          notifyListeners();
          continue;
        }
      }
    } catch (e) {
      _markReplyFailed(message, const _FailedReply());
      if (playResponseAudio) {
        await OmiVoicePlaybackService.instance.interrupt();
      }
      completeChat(ProductOutcome.failure, failure: ProductFailure.network);
      notifyListeners();
    } finally {
      _voiceSendInFlight = false;
    }

    setShowTypingIndicator(false);
    if (!chatAttemptCompleted) {
      completeChat(ProductOutcome.failure, failure: ProductFailure.incomplete);
    }
  }

  Future sendMessageStreamToServer(String text, {ChatPageContext? context}) => _streamReply(text, context: context);

  /// Streams the reply to [text]. [retryFileIds] resends a failed message's attachments without
  /// touching the files currently selected in the composer (see [retryFailedReply]).
  Future<void> _streamReply(String text, {ChatPageContext? context, List<String>? retryFileIds}) async {
    _chatQuotaExceeded = false; // Clear stale quota state from previous sends
    aiStreamProgress = 0.0;
    // If Omi was still speaking a prior voice reply, stop it — the user's
    // typed message takes precedence.
    if (OmiVoicePlaybackService.instance.isSpeaking) {
      await OmiVoicePlaybackService.instance.interrupt();
    }
    setShowTypingIndicator(true);
    var currentAppId = appProvider?.selectedChatAppId;
    if (currentAppId == 'no_selected') {
      currentAppId = null;
    }

    String chatTargetId = currentAppId ?? 'omi';
    bool isPersonaChat = false;

    PlatformManager.instance.analytics.chatMessageSent(
      message: text,
      includesFiles: uploadedFiles.isNotEmpty,
      numberOfFiles: uploadedFiles.length,
      chatTargetId: chatTargetId,
      isPersonaChat: isPersonaChat,
      isVoiceInput: _isNextMessageFromVoice,
    );
    _isNextMessageFromVoice = false;

    final chatAttempt = ProductTelemetry.instance.start(
      ProductJourney.chatText,
      surface: ProductSurface.chat,
    );
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
    final failedReply = _FailedReply(text: text, context: context, fileIds: fileIds);
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
      await for (var chunk in (replyStreamOverride ?? sendMessageStreamServer)(
        text,
        appId: currentAppId,
        filesId: fileIds,
        context: context,
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
          message = chunk.message!;
          messages[aiIndex] = message;
          _transferChatTelemetryAttempt(responseMessageId, message.id);
          _finishChatTelemetryAttempt(message.id, ProductOutcome.success);
          chatAttemptCompleted = true;
          notifyListeners();
          continue;
        }

        if (chunk.type == MessageChunkType.error) {
          if (_tryParseQuotaError(chunk.text)) {
            // Keep the user's message visible; replace AI placeholder with quota message
            final l10n = globalNavigatorKey.currentContext?.l10n;
            message.text = l10n?.chatQuotaExceededReply ??
                "You've hit your monthly limit. Upgrade to keep chatting with Omi without restrictions.";
            completeChat(ProductOutcome.failure, failure: ProductFailure.quota);
            notifyListeners();
            return;
          }
          Logger.debug('Chat reply failed: ${chunk.text}');
          _markReplyFailed(message, failedReply);
          completeChat(ProductOutcome.failure, failure: ProductFailure.server);
          notifyListeners();
          continue;
        }
      }
    } catch (e) {
      _markReplyFailed(message, failedReply);
      completeChat(ProductOutcome.failure, failure: ProductFailure.network);
      notifyListeners();
    } finally {
      timer?.cancel();
      flushBuffer();
      aiStreamProgress = 1.0;
      setShowTypingIndicator(false);
      setSendingMessage(false);
    }
    if (!chatAttemptCompleted) {
      completeChat(ProductOutcome.failure, failure: ProductFailure.incomplete);
    }
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
    for (final state in _chatTelemetryAttempts.values) {
      state.dispose();
      if (!state.attempt.isComplete) state.attempt.complete(ProductOutcome.unobserved);
    }
    _chatTelemetryAttempts.clear();
    super.dispose();
  }
}
