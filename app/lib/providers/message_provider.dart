import 'dart:async';
import 'dart:io';

import 'package:collection/collection.dart';
import 'package:file_picker/file_picker.dart';
import 'package:flutter/foundation.dart';
import 'package:flutter/material.dart';
import 'package:flutter/services.dart';
import 'package:omi/backend/http/api/apps.dart';
import 'package:omi/backend/http/api/messages.dart';
import 'package:omi/backend/http/api/users.dart';
import 'package:omi/backend/preferences.dart';
import 'package:omi/backend/schema/app.dart';
import 'package:omi/backend/schema/bt_device/bt_device.dart';
import 'package:omi/backend/schema/message.dart';
import 'package:omi/providers/app_provider.dart';
import 'package:omi/utils/alerts/app_snackbar.dart';
import 'package:image_picker/image_picker.dart';
import 'package:omi/utils/file.dart';
import 'package:omi/utils/analytics/mixpanel.dart';
import 'package:omi/utils/platform/platform_service.dart';
import 'package:uuid/uuid.dart';

class MessageProvider extends ChangeNotifier {
  static late MethodChannel _askAIChannel;

  MessageProvider() {
    if (PlatformService.isDesktop) {
      _askAIChannel = const MethodChannel('com.omi/ask_ai');
      _askAIChannel.setMethodCallHandler(_handleAskAIMethodCall);
    }
  }

  AppProvider? appProvider;
  List<ServerMessage> messages = [];
  bool _isNextMessageFromVoice = false;

  bool isLoadingMessages = false;
  bool hasCachedMessages = false;
  bool isClearingChat = false;
  bool showTypingIndicator = false;
  bool sendingMessage = false;
  double aiStreamProgress = 1.0;

  String firstTimeLoadingText = '';

  List<App> chatApps = [];
  bool isLoadingChatApps = false;

  List<File> selectedFiles = [];
  List<String> selectedFileTypes = [];
  List<MessageFile> uploadedFiles = [];
  bool isUploadingFiles = false;
  Map<String, bool> uploadingFiles = {};

  void updateAppProvider(AppProvider p) {
    appProvider = p;
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
      final result = await retrieveAppsSearch(
        installedApps: true,
        limit: 50,
      );

      chatApps = result.apps.where((app) => app.worksWithChat()).toList();
    } catch (e) {
      debugPrint('Error fetching chat apps: $e');
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

  Future<List<MessageFile>?> uploadFiles(List<File> files, String? appId) async {
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
      return res;
    }

    return null;
  }

  void removeLocalMessage(String id) {
    messages.removeWhere((m) => m.id == id);
    notifyListeners();
  }

  Future refreshMessages({bool dropdownSelected = false}) async {
    setLoadingMessages(true);
    if (SharedPreferencesUtil().cachedMessages.isNotEmpty) {
      setHasCachedMessages(true);
    }
    messages = await getMessagesFromServer(dropdownSelected: dropdownSelected);
    if (messages.isEmpty) {
      messages = SharedPreferencesUtil().cachedMessages;
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
      messages = SharedPreferencesUtil().cachedMessages;
      messages.sort((a, b) => a.createdAt.compareTo(b.createdAt));
    }
    notifyListeners();
  }

  Future<List<ServerMessage>> getMessagesFromServer({bool dropdownSelected = false}) async {
    if (!hasCachedMessages) {
      firstTimeLoadingText = 'Reading your memories...';
      notifyListeners();
    }
    setLoadingMessages(true);
    var mes = await getMessagesServer(
      appId: appProvider?.selectedChatAppId,
      dropdownSelected: dropdownSelected,
    );
    if (!hasCachedMessages) {
      firstTimeLoadingText = 'Learning from your memories...';
      notifyListeners();
    }
    messages = mes;
    messages.sort((a, b) => a.createdAt.compareTo(b.createdAt));
    setLoadingMessages(false);
    notifyListeners();
    return messages;
  }

  Future setMessageNps(ServerMessage message, int value, {String? reason}) async {
    await setMessageResponseRating(message.id, value, reason: reason);
    message.askForNps = false;
    // Update local message rating so it persists when scrolling
    message.rating = value == 0 ? null : value;
    notifyListeners();
  }

  Future clearChat() async {
    setClearingChat(true);
    var mes = await clearChatServer(appId: appProvider?.selectedChatAppId);
    messages = mes;
    messages.sort((a, b) => a.createdAt.compareTo(b.createdAt));
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
      false,
      List.from(uploadedFiles),
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
    messages.add(message);
    var aiIndex = messages.length - 1;
    notifyListeners();

    try {
      bool firstChunkRecieved = false;
      await for (var chunk in sendVoiceMessageStreamServer([file])) {
        if (!firstChunkRecieved &&
            [MessageChunkType.message, MessageChunkType.data, MessageChunkType.done, MessageChunkType.think]
                .contains(chunk.type)) {
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
          messages[aiIndex] = message;
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
    aiStreamProgress = 0.0;
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
    messages.add(message);
    final aiIndex = messages.length - 1;
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
        aiStreamProgress = (aiStreamProgress + 0.05).clamp(0.0, 1.0);
        HapticFeedback.lightImpact();
        notifyListeners();
      }
    }

    try {
      await for (var chunk in sendMessageStreamServer(text, appId: currentAppId, filesId: fileIds)) {
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
          messages[aiIndex] = message;
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
    } finally {
      timer?.cancel();
      flushBuffer();
      aiStreamProgress = 1.0;
      setShowTypingIndicator(false);
      setSendingMessage(false);
    }
  }

  Future sendInitialAppMessage(App? app) async {
    setSendingMessage(true);
    ServerMessage message = await getInitialAppMessage(app?.id);
    addMessage(message);
    setSendingMessage(false);
    notifyListeners();
  }

  App? messageSenderApp(String? appId) {
    return appProvider?.apps.firstWhereOrNull((p) => p.id == appId);
  }

  Future<void> _handleAskAIMethodCall(MethodCall call) async {
    if (!PlatformService.isDesktop) {
      return;
    }
    switch (call.method) {
      case 'sendQuery':
        final args = call.arguments as Map<dynamic, dynamic>;
        final message = args['message'] as String;
        final filePath = args['filePath'] as String?;

        List<String>? fileIds;
        if (filePath != null && filePath.isNotEmpty) {
          final file = File(filePath);
          final uploadedFilesResult = await uploadFiles([file], null);
          if (uploadedFilesResult != null) {
            fileIds = uploadedFilesResult.map((f) => f.id).toList();
          } else {
            _askAIChannel.invokeMethod('aiResponseChunk', {
              'type': 'error',
              'text': 'Failed to upload the attached file.',
            });
            return;
          }
        }

        try {
          await for (var chunk in sendMessageStreamServer(message, filesId: fileIds)) {
            final chunkMap = {
              'type': chunk.type.toString().split('.').last,
              'text': chunk.text,
              'messageId': chunk.messageId,
            };
            if (chunk.type == MessageChunkType.done && chunk.message != null) {
              chunkMap['text'] = chunk.message!.text;
            }
            _askAIChannel.invokeMethod('aiResponseChunk', chunkMap);
          }
        } catch (e) {
          final failedChunk = ServerMessageChunk.failedMessage();
          final chunkMap = {
            'type': failedChunk.type.toString().split('.').last,
            'text': failedChunk.text,
            'messageId': failedChunk.messageId,
          };
          _askAIChannel.invokeMethod('aiResponseChunk', chunkMap);
        }
        break;
      default:
        throw PlatformException(
          code: 'Unimplemented',
          details: 'Method ${call.method} not implemented.',
        );
    }
  }
}
