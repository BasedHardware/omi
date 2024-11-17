import 'dart:io';

import 'package:flutter/cupertino.dart';
import 'package:flutter/material.dart';
import 'package:flutter/services.dart';
import 'package:flutter/widgets.dart';
import 'package:friend_private/backend/http/api/apps.dart';
import 'package:friend_private/backend/preferences.dart';
import 'package:friend_private/backend/schema/app.dart';
import 'package:friend_private/providers/app_provider.dart';
import 'package:friend_private/utils/alerts/app_snackbar.dart';
import 'package:friend_private/widgets/extensions/string.dart';
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
  TextEditingController authUrlController = TextEditingController();

  bool termsAgreed = false;

  bool makeAppPublic = false;

  List<Category> categories = [];

  File? imageFile;
  String? imageUrl;
  String? updateAppId;
  List<AppCapability> selectedCapabilities = [];
  List<NotificationScope> selectedScopes = [];
  List<AppCapability> capabilities = [];

  bool isLoading = false;
  bool isUpdating = false;
  bool isSubmitting = false;

  void setAppProvider(AppProvider provider) {
    appProvider = provider;
  }

  Future init() async {
    setIsLoading(true);
    if (categories.isEmpty) {
      await getCategories();
    }
    if (capabilities.isEmpty) {
      await getAppCapabilities();
    }
    creatorNameController.text = SharedPreferencesUtil().givenName;
    creatorEmailController.text = SharedPreferencesUtil().email;
    setIsLoading(false);
  }

  void setIsLoading(bool loading) {
    isLoading = loading;
    notifyListeners();
  }

  void setIsUpdating(bool updating) {
    isUpdating = updating;
    notifyListeners();
  }

  void setIsSubmitting(bool submitting) {
    isSubmitting = submitting;
    notifyListeners();
  }

  Future prepareUpdate(App app) async {
    setIsLoading(true);
    if (capabilities.isEmpty) {
      await getAppCapabilities();
    }
    if (categories.isEmpty) {
      await getCategories();
    }
    setAppCategory(app.category);
    termsAgreed = true;
    updateAppId = app.id;
    imageUrl = app.image;
    appNameController.text = app.name.decodeString;
    appDescriptionController.text = app.description.decodeString;
    creatorNameController.text = app.author.decodeString;
    creatorEmailController.text = app.email ?? '';
    makeAppPublic = !app.private;
    selectedCapabilities = app.getCapabilitiesFromIds(capabilities);
    if (app.externalIntegration != null) {
      triggerEvent = app.externalIntegration!.triggersOn;
      webhookUrlController.text = app.externalIntegration!.webhookUrl;
      setupCompletedController.text = app.externalIntegration!.setupCompletedUrl ?? '';
      instructionsController.text = app.externalIntegration!.setupInstructionsFilePath;
      if (app.externalIntegration!.authSteps.isNotEmpty) {
        authUrlController.text = app.externalIntegration!.authSteps.first.url;
      }
    }
    if (app.chatPrompt != null) {
      chatPromptController.text = app.chatPrompt!.decodeString;
    }
    if (app.memoryPrompt != null) {
      memoryPromptController.text = app.memoryPrompt!.decodeString;
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
    authUrlController.clear();
    termsAgreed = false;
    makeAppPublic = false;
    appCategory = null;
    imageFile = null;
    imageUrl = null;
    selectedScopes.clear();
    updateAppId = null;
    selectedCapabilities.clear();
  }

  Future<void> getCategories() async {
    categories = await getAppCategories();
    appProvider!.categories = categories;
    notifyListeners();
  }

  Future<void> getAppCapabilities() async {
    capabilities = await getAppCapabilitiesServer();
    appProvider!.capabilities = capabilities;
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
    if (selectedCapabilities.length != app.capabilities.length) {
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
      if (selectedCapabilities.length == 1 && selectedCapabilities.first.id == 'proactive_notification') {
        if (selectedScopes.isEmpty) {
          AppSnackbar.showSnackbarError('Please select one more core capability for your app to proceed');
          return false;
        }
      }
      if (!termsAgreed) {
        AppSnackbar.showSnackbarError('Please agree to the terms and conditions to proceed');
        return false;
      }
      if (!capabilitySelected()) {
        AppSnackbar.showSnackbarError('Please select at least one capability for your app');
        return false;
      }
      if (imageFile == null && imageUrl == null) {
        AppSnackbar.showSnackbarError('Please select a logo for your app');
        return false;
      }
      for (var capability in selectedCapabilities) {
        if (capability.title == 'chat') {
          if (chatPromptController.text.isEmpty) {
            AppSnackbar.showSnackbarError('Please enter a chat prompt for your app');
            return false;
          }
        }
        if (capability.title == 'memories') {
          if (memoryPromptController.text.isEmpty) {
            AppSnackbar.showSnackbarError('Please enter a memory prompt for your app');
            return false;
          }
        }
        if (capability.title == 'external_integration') {
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
      'capabilities': selectedCapabilities.map((e) => e.id).toList(),
      'deleted': false,
      'uid': SharedPreferencesUtil().uid,
      'category': appCategory,
      'private': !makeAppPublic,
      'id': updateAppId,
    };
    for (var capability in selectedCapabilities) {
      if (capability.id == 'external_integration') {
        data['external_integration'] = {
          'triggers_on': triggerEvent,
          'webhook_url': webhookUrlController.text,
          'setup_completed_url': setupCompletedController.text,
          'setup_instructions_file_path': instructionsController.text,
          'auth_steps': [],
        };
        if (authUrlController.text.isNotEmpty) {
          data['external_integration']['auth_steps'] = [];
          data['external_integration']['auth_steps'].add({
            'url': authUrlController.text,
            'name': 'Setup ${appNameController.text}',
          });
        }
      }
      if (capability.id == 'chat') {
        data['chat_prompt'] = chatPromptController.text;
      }
      if (capability.id == 'memories') {
        data['memory_prompt'] = memoryPromptController.text;
      }
      if (capability.id == 'proactive_notification') {
        if (data['proactive_notification'] == null) {
          data['proactive_notification'] = {};
        }
        data['proactive_notification']['scopes'] = selectedScopes.map((e) => e.id).toList();
      }
    }
    var res = await updateAppServer(imageFile, data);
    if (res) {
      var app = await getAppDetailsServer(updateAppId!);
      appProvider!.updateLocalApp(App.fromJson(app!));
      AppSnackbar.showSnackbarSuccess('App updated successfully 🚀');
      clear();
      appProvider!.getApps();
    } else {
      AppSnackbar.showSnackbarError('Failed to update app. Please try again later');
    }
    setIsUpdating(false);
  }

  Future<void> submitApp() async {
    setIsSubmitting(true);
    Map<String, dynamic> data = {
      'name': appNameController.text,
      'description': appDescriptionController.text,
      'author': creatorNameController.text,
      'email': creatorEmailController.text,
      'capabilities': selectedCapabilities.map((e) => e.id).toList(),
      'deleted': false,
      'uid': SharedPreferencesUtil().uid,
      'category': appCategory,
      'private': !makeAppPublic,
    };
    for (var capability in selectedCapabilities) {
      if (capability.id == 'external_integration') {
        data['external_integration'] = {
          'triggers_on': triggerEvent,
          'webhook_url': webhookUrlController.text,
          'setup_completed_url': setupCompletedController.text,
          'setup_instructions_file_path': instructionsController.text,
          'auth_steps': [],
        };
        if (authUrlController.text.isNotEmpty) {
          data['external_integration']['auth_steps'] = [];
          data['external_integration']['auth_steps'].add({
            'url': authUrlController.text,
            'name': 'Setup ${appNameController.text}',
          });
        }
      }
      if (capability.id == 'chat') {
        data['chat_prompt'] = chatPromptController.text;
      }
      if (capability.id == 'memories') {
        data['memory_prompt'] = memoryPromptController.text;
      }
      if (capability.id == 'proactive_notification') {
        if (data['proactive_notification'] == null) {
          data['proactive_notification'] = {};
        }
        data['proactive_notification']['scopes'] = selectedScopes.map((e) => e.id).toList();
      }
    }
    var res = await submitAppServer(imageFile!, data);
    if (res) {
      AppSnackbar.showSnackbarSuccess('App submitted successfully 🚀');
      appProvider!.getApps();
      clear();
    } else {
      AppSnackbar.showSnackbarError('Failed to submit app. Please try again later');
    }
    setIsSubmitting(false);
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

  void addOrRemoveCapability(AppCapability capability) {
    if (selectedCapabilities.contains(capability)) {
      selectedCapabilities.remove(capability);
    } else {
      selectedCapabilities.add(capability);
    }
    notifyListeners();
  }

  bool isCapabilitySelected(AppCapability capability) {
    return selectedCapabilities.contains(capability);
  }

  void addOrRemoveScope(NotificationScope scope) {
    if (selectedScopes.contains(scope)) {
      selectedScopes.remove(scope);
    } else {
      selectedScopes.add(scope);
    }
    notifyListeners();
  }

  bool isScopesSelected(NotificationScope scope) {
    return selectedScopes.contains(scope);
  }

  bool isCapabilitySelectedById(String capability) {
    return selectedCapabilities.any((e) => e.id == capability);
  }

  List<TriggerEvent> getTriggerEvents() {
    return selectedCapabilities
        .where((element) => element.id == 'external_integration')
        .map((e) => e.triggerEvents)
        .expand((element) => element)
        .toList();
  }

  List<NotificationScope> getNotificationScopes() {
    return selectedCapabilities
        .where((item) => item.id == 'proactive_notification')
        .map((e) => e.notificationScopes)
        .expand((element) => element)
        .toList();
  }

  bool capabilitySelected() {
    if (selectedCapabilities.length == 1 && selectedCapabilities.first.id == 'proactive_notification') {
      return false;
    } else {
      return selectedCapabilities.isNotEmpty;
    }
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
