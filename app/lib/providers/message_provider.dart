import 'dart:io';

import 'package:collection/collection.dart';
import 'package:file_picker/file_picker.dart';
import 'package:flutter/foundation.dart';
import 'package:flutter/material.dart';
import 'package:omi/backend/http/api/messages.dart';
import 'package:omi/backend/http/api/users.dart';
import 'package:omi/backend/preferences.dart';
import 'package:omi/backend/schema/app.dart';
import 'package:omi/backend/schema/message.dart';
import 'package:omi/providers/app_provider.dart';
import 'package:omi/utils/alerts/app_snackbar.dart';
import 'package:image_picker/image_picker.dart';
import 'package:omi/utils/file.dart';
import 'package:uuid/uuid.dart';

class MessageProvider extends ChangeNotifier {
  AppProvider? appProvider;
  List<ServerMessage> messages = [];

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

  void updateAppProvider(AppProvider p) {
    appProvider = p;
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
    var res = await ImagePicker().pickImage(source: ImageSource.camera);
    if (res != null) {
      selectedFiles.add(File(res.path));
      selectedFileTypes.add('image');
      var index = selectedFiles.length - 1;
      await uploadFiles([selectedFiles[index]], appProvider?.selectedChatAppId);
      notifyListeners();
    }
  }

  void selectImage() async {
    if (selectedFiles.length >= 4) {
      AppSnackbar.showSnackbarError('You can only select up to 4 images');
      return;
    }
    List res = [];
    if (4 - selectedFiles.length == 1) {
      res = [await ImagePicker().pickImage(source: ImageSource.gallery)];
    } else {
      res = await ImagePicker().pickMultiImage(limit: 4 - selectedFiles.length);
    }
    if (res.isNotEmpty) {
      List<File> files = [];
      for (var r in res) {
        files.add(File(r.path));
      }
      if (files.isNotEmpty) {
        selectedFiles.addAll(files);
        selectedFileTypes.addAll(res.map((e) => 'image'));
        await uploadFiles(files, appProvider?.selectedChatAppId);
      }
      notifyListeners();
    }
  }

  void selectFile() async {
    var res = await FilePicker.platform.pickFiles(
        type: FileType.custom,
        allowMultiple: true,
        allowedExtensions: ['jpeg', 'md', 'pdf', 'gif', 'doc', 'png', 'pptx', 'txt', 'xlsx', 'webp']);
    if (res != null) {
      List<File> files = [];
      for (var r in res.files) {
        files.add(File(r.path!));
      }
      if (files.isNotEmpty) {
        selectedFiles.addAll(files);
        selectedFileTypes.addAll(res.files.map((e) => 'file'));
        await uploadFiles(files, appProvider?.selectedChatAppId);
      }

      notifyListeners();
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
    setLoadingMessages(false);
    notifyListeners();
  }

  void setMessagesFromCache() {
    if (SharedPreferencesUtil().cachedMessages.isNotEmpty) {
      setHasCachedMessages(true);
      messages = SharedPreferencesUtil().cachedMessages;
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
      pluginId: appProvider?.selectedChatAppId,
      dropdownSelected: dropdownSelected,
    );
    if (!hasCachedMessages) {
      firstTimeLoadingText = 'Learning from your memories...';
      notifyListeners();
    }
    messages = mes;
    setLoadingMessages(false);
    notifyListeners();
    return messages;
  }

  Future setMessageNps(ServerMessage message, int value) async {
    await setMessageResponseRating(message.id, value);
    message.askForNps = false;
    notifyListeners();
  }

  Future clearChat() async {
    setClearingChat(true);
    var mes = await clearChatServer(pluginId: appProvider?.selectedChatAppId);
    messages = mes;
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

  Future sendVoiceMessageStreamToServer(List<List<int>> audioBytes, {Function? onFirstChunkRecived}) async {
    var file = await FileUtils.saveAudioBytesToTempFile(
      audioBytes,
      DateTime.now().millisecondsSinceEpoch ~/ 1000 - (audioBytes.length / 100).ceil(),
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
          messages[0] = message;
          notifyListeners();
          continue;
        }

        if (chunk.type == MessageChunkType.message) {
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
    var appId = appProvider?.selectedChatAppId;
    if (appId == 'no_selected') {
      appId = null;
    }
    var message = ServerMessage.empty(appId: appId);
    messages.insert(0, message);
    notifyListeners();
    List<String> fileIds = uploadedFiles.map((e) => e.id).toList();
    clearSelectedFiles();
    clearUploadedFiles();
    try {
      await for (var chunk in sendMessageStreamServer(text, appId: appProvider?.selectedChatAppId, filesId: fileIds)) {
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
          messages[0] = message;
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

  Future sendMessageToServer(String message, String? appId) async {
    setShowTypingIndicator(true);
    messages.insert(0, ServerMessage.empty(appId: appId));
    List<String> fileIds = uploadedFiles.map((e) => e.id).toList();
    var mes = await sendMessageServer(message, appId: appId, fileIds: fileIds);
    if (messages[0].id == '0000') {
      messages[0] = mes;
    }
    setShowTypingIndicator(false);
    notifyListeners();
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
}
