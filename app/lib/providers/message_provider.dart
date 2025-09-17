import 'dart:async';
import 'dart:io';

import 'package:collection/collection.dart';
import 'package:file_picker/file_picker.dart';
import 'package:flutter/foundation.dart';
import 'package:flutter/material.dart';
import 'package:flutter/services.dart';
import 'package:omi/backend/http/api/messages.dart';
import 'package:omi/backend/schema/app.dart';
import 'package:omi/backend/schema/bt_device/bt_device.dart';
import 'package:omi/backend/schema/message.dart';
import 'package:omi/providers/app_provider.dart';
import 'package:omi/utils/alerts/app_snackbar.dart';
import 'package:omi/backend/http/api/users.dart';
import 'package:image_picker/image_picker.dart';
import 'package:omi/utils/file.dart';
import 'package:omi/utils/analytics/mixpanel.dart';
import 'package:omi/utils/platform/platform_service.dart';
import 'package:uuid/uuid.dart';
import 'package:omi/utils/date_presets.dart';

class MessageProvider extends ChangeNotifier {
  AppProvider? appProvider;
  List<ServerMessage> messages = [];
  String? currentChatSessionId;
  bool _isNextMessageFromVoice = false;

  bool isLoadingMessages = false;
  bool hasCachedMessages = false;
  bool isClearingChat = false;
  bool showTypingIndicator = false;
  bool sendingMessage = false;

  String firstTimeLoadingText = '';

  List<File> selectedFiles = [];
  List<String> selectedFileTypes = [];
  List<MessageFile> uploadedFiles = [];
  bool isUploadingFiles = false;
  Map<String, bool> uploadingFiles = {};
  List<Map<String, dynamic>> sessions = [];

  // Blank draft guard to prevent background repopululation (i.e. re-gaining internet connection)
  bool isBlankDraft = false;

  // UI-driven retrieval controls
  DateTime? _dateRangeStartUtc;
  DateTime? _dateRangeEndUtc;
  final List<String> _scopedConversationIds = [];
  int _datePreset = 0; // 0: All, 1: Today, 2: Yesterday, 3: Last7, 4: Last30

  void clearRetrievalScope() {
    _scopedConversationIds.clear();
    notifyListeners();
  }

  void scopeToConversation(String id) {
    _scopedConversationIds
      ..clear()
      ..add(id);
    notifyListeners();
  }

  void setDateRange(DateTime? startUtc, DateTime? endUtc) {
    _dateRangeStartUtc = startUtc;
    _dateRangeEndUtc = endUtc;
    notifyListeners();
  }

  List<String> get scopedConversationIds => List.unmodifiable(_scopedConversationIds);
  DateTime? get dateRangeStartUtc => _dateRangeStartUtc;
  DateTime? get dateRangeEndUtc => _dateRangeEndUtc;
  int get datePreset => _datePreset;

  void setDatePreset(int preset) {
    _datePreset = preset;
    DateTime? s;
    DateTime? e;

    final range = computeDateRangeUtc(preset);
    s = range.startUtc;
    e = range.endExclusiveUtc;

    _dateRangeStartUtc = s;
    _dateRangeEndUtc = e;
    notifyListeners();
  }

  void updateAppProvider(AppProvider p) {
    appProvider = p;
  }

  void setCurrentChatSessionId(String? id) {
    currentChatSessionId = id;
    notifyListeners();
  }

  Future<void> startNewChat({String? appId}) async {
    if (appId != null) {
      appProvider?.setSelectedChatAppId(appId);
    }
    setCurrentChatSessionId(null);
    setLoadingMessages(false);
    messages = [];
    clearRetrievalScope();
    setDatePreset(0);
    clearSelectedFiles();
    clearUploadedFiles();
    isBlankDraft = true;
    notifyListeners();
  }

  Future<void> startScopedChat(String conversationId, {String? appId}) async {
    await startNewChat(appId: appId);
    scopeToConversation(conversationId);
  }

  Future<void> loadSessions({int limit = 20}) async {
    try {
      final list = await listChatSessionsServer(limit: limit);
      sessions = list;
      notifyListeners();
    } catch (_) {}
  }

  Future<void> switchToSession(String id) async {
    final session = await getChatSessionServer(id);
    final String? pluginId = (session['plugin_id'] as String?);
    appProvider?.setSelectedChatAppId(pluginId);
    setCurrentChatSessionId(id);
    setLoadingMessages(true);
    messages = [];
    await refreshMessages();
    setLoadingMessages(false);
    notifyListeners();
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

  // Helper: adopt a session id from a streamed message if we don't have one yet
  bool _adoptSessionIdFromMessage(ServerMessage? message) {
    final bool noSessionYet = currentChatSessionId == null || currentChatSessionId!.isEmpty;
    final String? newSessionId = message?.chatSessionId;
    final bool chunkHasSession = newSessionId != null && newSessionId.isNotEmpty;
    if (noSessionYet && chunkHasSession) {
      setCurrentChatSessionId(newSessionId);
      isBlankDraft = false;
      return true;
    }
    return false;
  }

  void captureImage() async {
    if (PlatformService.isDesktop) {
      AppSnackbar.showSnackbarError('Camera capture is not available on this platform');
      return;
    }

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
        AppSnackbar.showSnackbarError('Camera permission denied. Please allow access to camera');
      } else {
        AppSnackbar.showSnackbarError('Error accessing camera: ${e.message ?? e.code}');
      }
    } catch (e) {
      AppSnackbar.showSnackbarError('Error taking photo. Please try again.');
    }
  }

  void selectImage() async {
    if (selectedFiles.length >= 4) {
      AppSnackbar.showSnackbarError('You can only select up to 4 images');
      return;
    }

    try {
      List<File> files = [];

      if (PlatformService.isDesktop) {
        try {
          FilePickerResult? result = await FilePicker.platform.pickFiles(
            type: FileType.custom,
            allowedExtensions: ['jpg', 'jpeg', 'png', 'gif', 'bmp', 'webp'],
            allowMultiple: true,
            dialogTitle: 'Select image files',
            withData: false,
            withReadStream: false,
          );

          if (result != null && result.files.isNotEmpty) {
            for (var file in result.files) {
              if (file.path != null && files.length < (4 - selectedFiles.length)) {
                files.add(File(file.path!));
              }
            }
          } else {
            return;
          }
        } on PlatformException catch (e) {
          AppSnackbar.showSnackbarError('Error opening file picker: ${e.message}');
          return;
        } catch (e) {
          debugPrint('FilePicker general error: $e');
          AppSnackbar.showSnackbarError('Error selecting images: $e');
          return;
        }
      } else {
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
      }

      if (files.isNotEmpty) {
        selectedFiles.addAll(files);
        selectedFileTypes.addAll(files.map((e) => 'image'));
        await uploadFiles(files, appProvider?.selectedChatAppId);
      }
      notifyListeners();
    } on PlatformException catch (e) {
      debugPrint('🖼️ PlatformException during image picking: ${e.code} - ${e.message}');
      if (e.code == 'photo_access_denied') {
        AppSnackbar.showSnackbarError('Photos permission denied. Please allow access to photos to select images');
      } else {
        AppSnackbar.showSnackbarError('Error selecting images: ${e.message ?? e.code}');
      }
    } catch (e) {
      debugPrint('🖼️ General exception during image picking: $e');
      AppSnackbar.showSnackbarError('Error selecting images. Please try again.');
    }
  }

  void selectFile() async {
    if (selectedFiles.length >= 4) {
      AppSnackbar.showSnackbarError('You can only select up to 4 files');
      return;
    }

    try {
      var res = await FilePicker.platform.pickFiles(
        type: FileType.custom,
        allowMultiple: true,
        allowedExtensions: ['jpeg', 'md', 'pdf', 'gif', 'doc', 'png', 'pptx', 'txt', 'xlsx', 'webp'],
        dialogTitle: 'Select files',
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
      AppSnackbar.showSnackbarError('Error selecting files: ${e.message ?? e.code}');
    } catch (e) {
      AppSnackbar.showSnackbarError('Error selecting files. Please try again.');
    }
  }

  void clearSelectedFile(int index) {
    selectedFiles.removeAt(index);
    selectedFileTypes.removeAt(index);
    uploadedFiles.removeAt(index);
    notifyListeners();
  }

  void clearSelectedFiles() {
    selectedFiles.clear();
    selectedFileTypes.clear();
    notifyListeners();
  }

  void clearUploadedFiles() {
    uploadedFiles.clear();
    notifyListeners();
  }

  Future<void> uploadFiles(List<File> files, String? appId) async {
    if (files.isNotEmpty) {
      setMultiUploadingFileStatus(files.map((e) => e.path).toList(), true);
      var res = await uploadFilesServer(files, appId: appId);
      if (res != null) {
        uploadedFiles.addAll(res);
      } else {
        clearSelectedFiles();
        AppSnackbar.showSnackbarError('Failed to upload file, please try again later');
      }
      setMultiUploadingFileStatus(files.map((e) => e.path).toList(), false);
      notifyListeners();
    }
  }

  void removeLocalMessage(String id) {
    messages.removeWhere((m) => m.id == id);
    notifyListeners();
  }

  Future refreshMessages({bool dropdownSelected = false}) async {
    if (currentChatSessionId == null && isBlankDraft) {
      setLoadingMessages(false);
      notifyListeners();
      return;
    }
    setLoadingMessages(true);
    setHasCachedMessages(false);
    messages = await getMessagesServer(
      chatSessionId: currentChatSessionId,
      dropdownSelected: dropdownSelected,
    );
    setLoadingMessages(false);
    notifyListeners();
  }

  Future clearChat() async {
    setClearingChat(true);
    await clearChatServer(chatSessionId: currentChatSessionId);
    await startNewChat(appId: appProvider?.selectedChatAppId);
    setClearingChat(false);
    notifyListeners();
  }

  void addMessageLocally(String messageText) {
    List<String> fileIds = uploadedFiles.map((e) => e.id).toList();
    var appId = appProvider?.selectedChatAppId;
    if (appId == 'no_selected') {
      appId = null;
    }
    var message = ServerMessage(
      const Uuid().v4(),
      DateTime.now(),
      messageText,
      MessageSender.human,
      MessageType.text,
      appId,
      null,
      false,
      List.from(uploadedFiles),
      fileIds,
      [],
    );
    if (messages.firstWhereOrNull((m) => m.id == message.id) != null) {
      return;
    }
    messages.insert(0, message);
    notifyListeners();
  }

  void addMessage(ServerMessage message) {
    if (messages.firstWhereOrNull((m) => m.id == message.id) != null) {
      return;
    }
    messages.insert(0, message);
    notifyListeners();
  }

  Future sendVoiceMessageStreamToServer(List<List<int>> audioBytes,
      {Function? onFirstChunkRecived, BleAudioCodec? codec}) async {
    var file = await FileUtils.saveAudioBytesToTempFile(
      audioBytes,
      DateTime.now().millisecondsSinceEpoch ~/ 1000 - (audioBytes.length / 100).ceil(),
      codec?.getFrameSize() ?? 160,
    );

    var currentAppId = appProvider?.selectedChatAppId;
    if (currentAppId == 'no_selected') {
      currentAppId = null;
    }
    String chatTargetId = currentAppId ?? 'omi';
    App? targetApp = currentAppId != null ? appProvider?.apps.firstWhereOrNull((app) => app.id == currentAppId) : null;
    bool isPersonaChat = targetApp != null ? !targetApp.isNotPersona() : false;

    MixpanelManager().chatVoiceInputUsed(
      chatTargetId: chatTargetId,
      isPersonaChat: isPersonaChat,
    );

    setShowTypingIndicator(true);
    var message = ServerMessage.empty();
    messages.insert(0, message);
    notifyListeners();

    try {
      bool firstChunkRecieved = false;
      await for (var chunk in sendVoiceMessageStreamServer([file])) {
        if (!firstChunkRecieved && [MessageChunkType.data, MessageChunkType.done].contains(chunk.type)) {
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
          notifyListeners();
          continue;
        }

        if (chunk.type == MessageChunkType.done) {
          message = chunk.message!;
          _adoptSessionIdFromMessage(chunk.message);
          messages[0] = message;
          notifyListeners();
          continue;
        }

        if (chunk.type == MessageChunkType.message) {
          _adoptSessionIdFromMessage(chunk.message);
          messages.insert(1, chunk.message!);
          notifyListeners();
          continue;
        }

        if (chunk.type == MessageChunkType.error) {
          message.text = chunk.text;
          notifyListeners();
          continue;
        }
      }
    } catch (e) {
      message.text = ServerMessageChunk.failedMessage().text;
      notifyListeners();
    }

    setShowTypingIndicator(false);
  }

  Future sendMessageStreamToServer(String text) async {
    setShowTypingIndicator(true);
    var currentAppId = appProvider?.selectedChatAppId;
    if (currentAppId == 'no_selected') {
      currentAppId = null;
    }

    String chatTargetId = currentAppId ?? 'omi';
    App? targetApp = currentAppId != null ? appProvider?.apps.firstWhereOrNull((app) => app.id == currentAppId) : null;
    bool isPersonaChat = targetApp != null ? !targetApp.isNotPersona() : false;

    MixpanelManager().chatMessageSent(
      message: text,
      includesFiles: uploadedFiles.isNotEmpty,
      numberOfFiles: uploadedFiles.length,
      chatTargetId: chatTargetId,
      isPersonaChat: isPersonaChat,
      isVoiceInput: _isNextMessageFromVoice,
    );
    _isNextMessageFromVoice = false;

    var message = ServerMessage.empty(appId: currentAppId);
    messages.insert(0, message);
    notifyListeners();
    List<String> fileIds = uploadedFiles.map((e) => e.id).toList();
    clearSelectedFiles();
    clearUploadedFiles();
    String textBuffer = '';
    Timer? timer;

    void flushBuffer() {
      if (textBuffer.isNotEmpty) {
        message.text += textBuffer;
        textBuffer = '';
        HapticFeedback.lightImpact();
        notifyListeners();
      }
    }

    try {
      String? sessionIdToUse = currentChatSessionId;
      // Build date range & optional conversation scoping
      final Map<String, dynamic> context = {};
      if (_dateRangeStartUtc != null && _dateRangeEndUtc != null) {
        context['date_range'] = {
          'start': _dateRangeStartUtc!.toIso8601String(),
          'end': _dateRangeEndUtc!.toIso8601String(),
        };
      }
      if (_scopedConversationIds.isNotEmpty) {
        context['conversation_ids'] = List<String>.from(_scopedConversationIds);
      }

      await for (var chunk in sendMessageStreamServer(text,
          appId: currentAppId, chatSessionId: sessionIdToUse, filesId: fileIds, context: context)) {
        if (chunk.type == MessageChunkType.think) {
          flushBuffer();
          message.thinkings.add(chunk.text);
          notifyListeners();
          continue;
        }

        if (chunk.type == MessageChunkType.data) {
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
          _adoptSessionIdFromMessage(chunk.message);
          messages[0] = message;
          notifyListeners();
          unawaited(loadSessions());
          continue;
        }

        if (chunk.type == MessageChunkType.error) {
          message.text = chunk.text;
          notifyListeners();
          continue;
        }
      }
    } catch (e) {
      message.text = ServerMessageChunk.failedMessage().text;
      notifyListeners();
    } finally {
      timer?.cancel();
      flushBuffer();
      setShowTypingIndicator(false);
    }
  }

  Future setMessageNps(ServerMessage message, int value) async {
    await setMessageResponseRating(message.id, value);
    message.askForNps = false;
    notifyListeners();
  }

  App? messageSenderApp(String? appId) {
    return appProvider?.apps.firstWhereOrNull((p) => p.id == appId);
  }
}
