import 'dart:io';

import 'package:flutter/material.dart';
import 'package:flutter/services.dart';
import 'package:flutter/widgets.dart';
import 'package:friend_private/backend/http/api/apps.dart';
import 'package:friend_private/backend/preferences.dart';
import 'package:friend_private/backend/schema/app.dart';
import 'package:friend_private/providers/app_provider.dart';
import 'package:friend_private/utils/alerts/app_snackbar.dart';
import 'package:image_picker/image_picker.dart';

class AddAppProvider extends ChangeNotifier {
  AppProvider? appProvider;

  GlobalKey<FormState> formKey = GlobalKey<FormState>();

  TextEditingController appNameController = TextEditingController();
  TextEditingController appDescriptionController = TextEditingController();
  TextEditingController creatorNameController = TextEditingController();
  TextEditingController creatorEmailController = TextEditingController();
  TextEditingController chatPromptController = TextEditingController();
  TextEditingController memoryPromptController = TextEditingController();
  String? appCategory;

// Trigger Event
  String? triggerEvent;
  TextEditingController webhookUrlController = TextEditingController();
  TextEditingController setupCompletedController = TextEditingController();
  TextEditingController instructionsController = TextEditingController();

  bool termsAgreed = false;

  bool makeAppPublic = false;

  List<Category> categories = [];
  List<TriggerEvent> triggerEvents = [];
  List<NotificationScope> notificationScopes = [];

  File? imageFile;
  String? imageUrl;
  String? updateAppId;
  List<String> capabilities = [];

  bool isLoading = false;
  bool isUpdating = false;

  void setAppProvider(AppProvider provider) {
    appProvider = provider;
  }

  Future init() async {
    await getCategories();
    await getTriggerEvents();
    await getNotificationScopes();
    creatorNameController.text = SharedPreferencesUtil().givenName;
    creatorEmailController.text = SharedPreferencesUtil().email;
  }

  void setIsLoading(bool loading) {
    isLoading = loading;
    notifyListeners();
  }

  void setIsUpdating(bool updating) {
    isUpdating = updating;
    notifyListeners();
  }

  Future prepareUpdate(App app) async {
    setIsLoading(true);
    if (categories.isEmpty) {
      await getCategories();
    }
    var res = await getAppDetailsServer(app.id);
    setAppCategory(res!['category']);
    termsAgreed = true;
    updateAppId = app.id;
    imageUrl = app.image;
    appNameController.text = app.name;
    appDescriptionController.text = app.description;
    creatorNameController.text = app.author;
    creatorEmailController.text = res!['email'];
    makeAppPublic = !app.private;
    capabilities = app.capabilities.toList();
    if (app.externalIntegration != null) {
      triggerEvent = app.externalIntegration!.triggersOn;
      webhookUrlController.text = app.externalIntegration!.webhookUrl;
      setupCompletedController.text = app.externalIntegration!.setupCompletedUrl ?? '';
      instructionsController.text = app.externalIntegration!.setupInstructionsFilePath;
    }
    if (app.chatPrompt != null) {
      chatPromptController.text = app.chatPrompt!;
    }
    if (app.memoryPrompt != null) {
      memoryPromptController.text = app.memoryPrompt!;
    }
    setIsLoading(false);
    notifyListeners();
  }

  void clear() {
    appNameController.clear();
    appDescriptionController.clear();
    creatorNameController.clear();
    creatorEmailController.clear();
    chatPromptController.clear();
    memoryPromptController.clear();
    triggerEvent = null;
    webhookUrlController.clear();
    setupCompletedController.clear();
    instructionsController.clear();
    termsAgreed = false;
    makeAppPublic = false;
    appCategory = null;
    imageFile = null;
    imageUrl = null;
    capabilities.clear();
  }

  Future<void> getCategories() async {
    categories = await getAppCategories();
    notifyListeners();
  }

  Future<void> getTriggerEvents() async {
    triggerEvents = await getTriggerEventsServer();
    notifyListeners();
  }

  Future<void> getNotificationScopes() async {
    notificationScopes = await getNotificationScopesServer();
    notifyListeners();
  }

  bool hasDataChanged(App app, String category) {
    if (imageFile != null) {
      return true;
    }
    if (appNameController.text != app.name) {
      return true;
    }
    if (appDescriptionController.text != app.description) {
      return true;
    }
    if (creatorNameController.text != app.author) {
      return true;
    }
    if (makeAppPublic != !app.private) {
      return true;
    }
    if (appCategory != category) {
      return true;
    }
    if (capabilities.length != app.capabilities.length) {
      return true;
    }
    if (app.externalIntegration != null) {
      if (triggerEvent != app.externalIntegration!.triggersOn) {
        return true;
      }
      if (webhookUrlController.text != app.externalIntegration!.webhookUrl) {
        return true;
      }
      if (setupCompletedController.text != app.externalIntegration!.setupCompletedUrl) {
        return true;
      }
      if (instructionsController.text != app.externalIntegration!.setupInstructionsFilePath) {
        return true;
      }
    }
    if (chatPromptController.text != app.chatPrompt) {
      return true;
    }
    if (memoryPromptController.text != app.memoryPrompt) {
      return true;
    }
    return false;
  }

  bool validateForm() {
    if (formKey.currentState!.validate()) {
      if (!termsAgreed) {
        AppSnackbar.showSnackbarError('Please agree to the terms and conditions to proceed');
        return false;
      }
      if (!capabilitySelected()) {
        AppSnackbar.showSnackbarError('Please select at least one capability for your app');
        return false;
      }
      if (imageFile == null && imageUrl == null) {
        print('imageFile: $imageFile');
        print('imageUrl: $imageUrl');
        AppSnackbar.showSnackbarError('Please select a logo for your app');
        return false;
      }
      if (isCapabilitySelected('external_integration')) {
        if (triggerEvent == null) {
          AppSnackbar.showSnackbarError('Please select a trigger event for your app');
          return false;
        }
        if (webhookUrlController.text.isEmpty) {
          AppSnackbar.showSnackbarError('Please enter a webhook URL for your app');
          return false;
        }
        if (setupCompletedController.text.isEmpty) {
          AppSnackbar.showSnackbarError('Please enter a setup completed URL for your app');
          return false;
        }
        if (instructionsController.text.isEmpty) {
          AppSnackbar.showSnackbarError('Please enter a setup instructions URL for your app');
          return false;
        }
      }
      if (isCapabilitySelected('chat')) {
        if (chatPromptController.text.isEmpty) {
          AppSnackbar.showSnackbarError('Please enter a chat prompt for your app');
          return false;
        }
      }
      if (isCapabilitySelected('memories')) {
        if (memoryPromptController.text.isEmpty) {
          AppSnackbar.showSnackbarError('Please enter a memory prompt for your app');
          return false;
        }
      }
      if (appCategory == null) {
        AppSnackbar.showSnackbarError('Please select a category for your app');
        return false;
      }
      return true;
    } else {
      AppSnackbar.showSnackbarError('Please fill in all the required fields correctly');
      return false;
    }
  }

  Future<void> updateApp() async {
    setIsUpdating(true);
    Map<String, dynamic> data = {
      'name': appNameController.text,
      'description': appDescriptionController.text,
      'author': creatorNameController.text,
      'email': creatorEmailController.text,
      'capabilities': capabilities,
      'deleted': false,
      'uid': SharedPreferencesUtil().uid,
      'category': appCategory,
      'private': !makeAppPublic,
      'id': updateAppId,
    };
    if (isCapabilitySelected('external_integration')) {
      data['external_integration'] = {
        'triggers_on': triggerEvent,
        'webhook_url': webhookUrlController.text,
        'setup_completed_url': setupCompletedController.text,
        'setup_instructions_file_path': instructionsController.text,
      };
    }
    if (isCapabilitySelected('chat')) {
      data['chat_prompt'] = chatPromptController.text;
    }
    if (isCapabilitySelected('memories')) {
      data['memory_prompt'] = memoryPromptController.text;
    }
    var res = await updateAppServer(imageFile, data);
    if (res) {
      var app = await getAppDetailsServer(updateAppId!);

      appProvider!.updateLocalApp(App.fromJson(app!));
      AppSnackbar.showSnackbarSuccess('App updated successfully 🚀');
      appProvider!.getApps();
      clear();
    } else {
      AppSnackbar.showSnackbarError('Failed to update app. Please try again later');
    }
    setIsUpdating(false);
  }

  Future<void> submitApp() async {
    setIsLoading(true);
    Map<String, dynamic> data = {
      'name': appNameController.text,
      'description': appDescriptionController.text,
      'author': creatorNameController.text,
      'email': creatorEmailController.text,
      'capabilities': capabilities,
      'deleted': false,
      'uid': SharedPreferencesUtil().uid,
      'category': appCategory,
      'private': !makeAppPublic,
    };
    if (isCapabilitySelected('external_integration')) {
      data['external_integration'] = {
        'triggers_on': triggerEvent,
        'webhook_url': webhookUrlController.text,
        'setup_completed_url': setupCompletedController.text,
        'setup_instructions_file_path': instructionsController.text,
      };
    }
    if (isCapabilitySelected('chat')) {
      data['chat_prompt'] = chatPromptController.text;
    }
    if (isCapabilitySelected('memories')) {
      data['memory_prompt'] = memoryPromptController.text;
    }
    var res = await submitAppServer(imageFile!, data);
    if (res) {
      AppSnackbar.showSnackbarSuccess('App submitted successfully 🚀');
      appProvider!.getApps();
      clear();
    } else {
      AppSnackbar.showSnackbarError('Failed to submit app. Please try again later');
    }
    setIsLoading(false);
  }

  Future pickImage() async {
    ImagePicker imagePicker = ImagePicker();
    try {
      var file = await imagePicker.pickImage(source: ImageSource.gallery);
      if (file != null) {
        imageFile = File(file.path);
      }
      notifyListeners();
    } on PlatformException catch (e) {
      if (e.code == 'photo_access_denied') {
        AppSnackbar.showSnackbarError('Photos permission denied. Please allow access to photos to select an image');
      }
    }
    notifyListeners();
  }

  Future updateImage() async {
    ImagePicker imagePicker = ImagePicker();
    try {
      var file = await imagePicker.pickImage(source: ImageSource.gallery);
      if (file != null) {
        print('file: ${file.path}');
        imageFile = File(file.path);
        imageUrl = null;
      }
      notifyListeners();
    } on PlatformException catch (e) {
      if (e.code == 'photo_access_denied') {
        AppSnackbar.showSnackbarError('Photos permission denied. Please allow access to photos to select an image');
      }
    }
    notifyListeners();
  }

  void addOrRemoveCapability(String capability) {
    if (capabilities.contains(capability)) {
      capabilities.remove(capability);
    } else {
      capabilities.add(capability);
    }
    notifyListeners();
  }

  bool isCapabilitySelected(String capability) {
    return capabilities.contains(capability);
  }

  bool capabilitySelected() {
    return capabilities.isNotEmpty;
  }

  void setTriggerEvent(String? event) {
    if (event == null) {
      return;
    }
    triggerEvent = event;
    notifyListeners();
  }

  void setTermsAgreed(bool? agreed) {
    if (agreed == null) {
      return;
    }
    termsAgreed = agreed;
    notifyListeners();
  }

  void setIsPrivate(bool? value) {
    print('private: $value');
    if (value == null) {
      return;
    }
    makeAppPublic = value;
    notifyListeners();
  }

  void setAppCategory(String? category) {
    if (category == null) {
      return;
    }
    appCategory = category;
    notifyListeners();
  }
}
