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
  GlobalKey<FormState> metadataKey = GlobalKey<FormState>();
  GlobalKey<FormState> externalIntegrationKey = GlobalKey<FormState>();
  GlobalKey<FormState> promptKey = GlobalKey<FormState>();
  GlobalKey<FormState> pricingKey = GlobalKey<FormState>();

  TextEditingController appNameController = TextEditingController();
  TextEditingController appDescriptionController = TextEditingController();
  TextEditingController chatPromptController = TextEditingController();
  TextEditingController conversationPromptController = TextEditingController();

  String? appCategory;

// Trigger Event
  String? triggerEvent;
  TextEditingController webhookUrlController = TextEditingController();
  TextEditingController setupCompletedController = TextEditingController();
  TextEditingController instructionsController = TextEditingController();
  TextEditingController authUrlController = TextEditingController();
  TextEditingController appHomeUrlController = TextEditingController();

  // Pricing
  TextEditingController priceController = TextEditingController();
  String? selectePaymentPlan;
  bool isPaid = false;

  List<PaymentPlan> paymentPlans = [];

  bool termsAgreed = false;

  bool makeAppPublic = false;

  List<Category> categories = [];

  File? imageFile;
  String? imageUrl;
  String? updateAppId;

  List<String> thumbnailUrls = [];
  List<String> thumbnailIds = [];
  bool isUploadingThumbnail = false;
  List<AppCapability> selectedCapabilities = [];
  List<NotificationScope> selectedScopes = [];
  List<AppCapability> capabilities = [];

  bool isLoading = false;
  bool isUpdating = false;
  bool isSubmitting = false;
  bool isValid = false;
  bool isGenratingDescription = false;

  bool allowPaidApps = false;

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
    if (paymentPlans.isEmpty) {
      await getPaymentPlans();
    }
    setIsLoading(false);
  }

  void setIsLoading(bool loading) {
    isLoading = loading;
    notifyListeners();
  }

  void setIsPaid(bool paid) {
    if (!paid) {
      priceController.clear();
      selectePaymentPlan = null;
    }
    isPaid = paid;
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
    if (paymentPlans.isEmpty) {
      await getPaymentPlans();
    }
    setAppCategory(app.category);
    setPaymentPlan(app.paymentPlan);
    isPaid = app.isPaid;
    termsAgreed = true;
    updateAppId = app.id;
    imageUrl = app.image;
    appNameController.text = app.name.decodeString;
    appDescriptionController.text = app.description.decodeString;
    priceController.text = app.price.toString();
    makeAppPublic = !app.private;
    selectedCapabilities = app.getCapabilitiesFromIds(capabilities);
    if (app.externalIntegration != null) {
      triggerEvent = app.externalIntegration!.triggersOn;
      webhookUrlController.text = app.externalIntegration!.webhookUrl;
      setupCompletedController.text = app.externalIntegration!.setupCompletedUrl ?? '';
      instructionsController.text = app.externalIntegration!.setupInstructionsFilePath;
      appHomeUrlController.text = app.externalIntegration!.appHomeUrl ?? '';
      if (app.externalIntegration!.authSteps.isNotEmpty) {
        authUrlController.text = app.externalIntegration!.authSteps.first.url;
      }
    }
    if (app.chatPrompt != null) {
      chatPromptController.text = app.chatPrompt!.decodeString;
    }
    if (app.conversationPrompt != null) {
      conversationPromptController.text = app.conversationPrompt!.decodeString;
    }
    if (app.proactiveNotification != null) {
      selectedScopes = app.getNotificationScopesFromIds(
          capabilities.firstWhere((element) => element.id == 'proactive_notification').notificationScopes);
    }

    // Set existing thumbnails
    thumbnailUrls = app.thumbnailUrls;
    thumbnailIds = app.thumbnailIds;
    isValid = false;
    setIsLoading(false);
    notifyListeners();
  }

  void clear() {
    appNameController.clear();
    appDescriptionController.clear();
    chatPromptController.clear();
    conversationPromptController.clear();
    triggerEvent = null;
    isPaid = false;
    selectePaymentPlan = null;
    webhookUrlController.clear();
    setupCompletedController.clear();
    instructionsController.clear();
    authUrlController.clear();
    appHomeUrlController.clear();
    priceController.clear();
    selectePaymentPlan = null;
    termsAgreed = false;
    makeAppPublic = false;
    appCategory = null;
    imageFile = null;
    imageUrl = null;
    selectedScopes.clear();
    updateAppId = null;
    selectedCapabilities.clear();
    thumbnailUrls = [];
    thumbnailIds = [];
  }

  void setPaymentPlan(String? plan) {
    if (plan == null) {
      return;
    }
    selectePaymentPlan = plan;
    notifyListeners();
  }

  Future<void> getPaymentPlans() async {
    paymentPlans = await getPaymentPlansServer();
    if (paymentPlans.isNotEmpty) {
      allowPaidApps = true;
    } else {
      allowPaidApps = false;
    }
    notifyListeners();
  }

  Future<void> getCategories() async {
    categories = await getAppCategories();
    appProvider!.categories = categories;
    notifyListeners();
  }

  String mapCategoryIdToName(String? id) {
    if (id == null) {
      return '';
    }
    return categories.firstWhere((element) => element.id == id).title;
  }

  String? mapTriggerEventIdToName(String? id) {
    if (id == null) {
      return null;
    }
    return getTriggerEvents().firstWhere((element) => element.id == id).title;
  }

  String? mapPaymentPlanIdToName(String? id) {
    if (id == null) {
      return null;
    }
    return paymentPlans.firstWhere((element) => element.id == id).title;
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
    if (conversationPromptController.text != app.conversationPrompt) {
      return true;
    }
    return false;
  }

  void checkValidity() {
    isValid = isFormValid();
    notifyListeners();
  }

  bool isFormValid() {
    if (capabilitySelected() && (imageFile != null || imageUrl != null) && appCategory != null && termsAgreed) {
      if (metadataKey.currentState != null && metadataKey.currentState!.validate()) {
        bool isValid = false;
        for (var capability in selectedCapabilities) {
          if (capability.id == 'external_integration') {
            if (triggerEvent == null) {
              isValid = false;
            } else {
              isValid = true;
            }
            if (externalIntegrationKey.currentState != null) {
              isValid = externalIntegrationKey.currentState!.validate();
            } else {
              isValid = false;
            }
          }
          if (capability.id == 'chat') {
            isValid = chatPromptController.text.isNotEmpty;
          }
          if (capability.id == 'memories') {
            isValid = conversationPromptController.text.isNotEmpty;
          }
          if (capability.id == 'proactive_notification') {
            isValid = selectedScopes.isNotEmpty && selectedCapabilities.length > 1;
          }
        }
        if (isPaid) {
          isValid = formKey.currentState!.validate() && selectePaymentPlan != null;
        }
        return isValid;
      } else {
        return false;
      }
    } else {
      return false;
    }
  }

  bool validateForm() {
    if (formKey.currentState!.validate()) {
      if (promptKey.currentState != null) {
        if (!promptKey.currentState!.validate()) {
          return false;
        }
      }
      if (metadataKey.currentState != null) {
        if (!metadataKey.currentState!.validate()) {
          return false;
        }
      }
      if (externalIntegrationKey.currentState != null) {
        if (!externalIntegrationKey.currentState!.validate()) {
          return false;
        }
      }
      if (pricingKey.currentState != null) {
        if (!pricingKey.currentState!.validate()) {
          return false;
        }
      }
      if (selectedCapabilities.length == 1 && selectedCapabilities.first.id == 'proactive_notification') {
        if (selectedScopes.isEmpty) {
          AppSnackbar.showSnackbarError('Please select one more core capability for your app to proceed');
          return false;
        }
      }
      if (isPaid && (priceController.text.isEmpty || selectePaymentPlan == null)) {
        AppSnackbar.showSnackbarError('Please select a payment plan and enter a price for your app');
        return false;
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
          if (conversationPromptController.text.isEmpty) {
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

  Future<bool> updateApp() async {
    setIsUpdating(true);

    Map<String, dynamic> data = {
      'name': appNameController.text,
      'description': appDescriptionController.text,
      'capabilities': selectedCapabilities.map((e) => e.id).toList(),
      'deleted': false,
      'uid': SharedPreferencesUtil().uid,
      'category': appCategory,
      'private': !makeAppPublic,
      'id': updateAppId,
      'is_paid': isPaid,
      'price': priceController.text.isNotEmpty ? double.parse(priceController.text) : 0.0,
      'payment_plan': selectePaymentPlan,
      'thumbnails': thumbnailIds,
    };
    for (var capability in selectedCapabilities) {
      if (capability.id == 'external_integration') {
        data['external_integration'] = {
          'triggers_on': triggerEvent,
          'webhook_url': webhookUrlController.text.trim(),
          'setup_completed_url': setupCompletedController.text.trim(),
          'setup_instructions_file_path': instructionsController.text.trim(),
          'app_home_url': appHomeUrlController.text.trim(),
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
        data['memory_prompt'] = conversationPromptController.text;
      }
      if (capability.id == 'proactive_notification') {
        if (data['proactive_notification'] == null) {
          data['proactive_notification'] = {};
        }
        data['proactive_notification']['scopes'] = selectedScopes.map((e) => e.id).toList();
      }
    }
    var success = false;
    var res = await updateAppServer(imageFile, data);
    if (res) {
      await appProvider!.getApps();
      var app = await getAppDetailsServer(updateAppId!);
      appProvider!.updateLocalApp(App.fromJson(app!));
      AppSnackbar.showSnackbarSuccess('App updated successfully 🚀');
      clear();
      success = true;
    } else {
      AppSnackbar.showSnackbarError('Failed to update app. Please try again later');
      success = false;
    }
    checkValidity();
    setIsUpdating(false);
    return success;
  }

  Future<String?> submitApp() async {
    setIsSubmitting(true);

    Map<String, dynamic> data = {
      'name': appNameController.text.trim(),
      'description': appDescriptionController.text.trim(),
      'capabilities': selectedCapabilities.map((e) => e.id).toList(),
      'deleted': false,
      'uid': SharedPreferencesUtil().uid,
      'category': appCategory,
      'private': !makeAppPublic,
      'is_paid': isPaid,
      'price': priceController.text.isNotEmpty ? double.parse(priceController.text) : 0.0,
      'payment_plan': selectePaymentPlan,
      'thumbnails': thumbnailIds,
    };
    for (var capability in selectedCapabilities) {
      if (capability.id == 'external_integration') {
        data['external_integration'] = {
          'triggers_on': triggerEvent,
          'webhook_url': webhookUrlController.text.trim(),
          'setup_completed_url': setupCompletedController.text.trim(),
          'setup_instructions_file_path': instructionsController.text.trim(),
          'app_home_url': appHomeUrlController.text.trim(),
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
        data['chat_prompt'] = chatPromptController.text.trim();
      }
      if (capability.id == 'memories') {
        data['memory_prompt'] = conversationPromptController.text.trim();
      }
      if (capability.id == 'proactive_notification') {
        if (data['proactive_notification'] == null) {
          data['proactive_notification'] = {};
        }
        data['proactive_notification']['scopes'] = selectedScopes.map((e) => e.id).toList();
      }
    }
    String? appId;
    var res = await submitAppServer(imageFile!, data);
    if (res.$1) {
      AppSnackbar.showSnackbarSuccess('App submitted successfully 🚀');
      await appProvider!.getApps();
      clear();
      appId = res.$3;
    } else {
      AppSnackbar.showSnackbarError(res.$2);
    }
    checkValidity();
    setIsSubmitting(false);
    return appId;
  }

  Future<void> pickThumbnail() async {
    ImagePicker imagePicker = ImagePicker();
    try {
      var file = await imagePicker.pickImage(
        source: ImageSource.gallery,
        imageQuality: 85,
      );
      if (file != null) {
        setIsUploadingThumbnail(true);
        var thumbnailFile = File(file.path);

        // Upload thumbnail
        var result = await uploadAppThumbnail(thumbnailFile);
        if (result.isNotEmpty) {
          thumbnailUrls.add(result['thumbnail_url']!);
          thumbnailIds.add(result['thumbnail_id']!);
        }
        setIsUploadingThumbnail(false);
      }
    } on PlatformException catch (e) {
      if (e.code == 'photo_access_denied') {
        AppSnackbar.showSnackbarError('Photos permission denied. Please allow access to photos to select an image');
      }
      setIsUploadingThumbnail(false);
    }
    checkValidity();
    notifyListeners();
  }

  void setIsUploadingThumbnail(bool uploading) {
    isUploadingThumbnail = uploading;
    notifyListeners();
  }

  void removeThumbnail(int index) {
    thumbnailUrls.removeAt(index);
    thumbnailIds.removeAt(index);
    checkValidity();
    notifyListeners();
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
    checkValidity();
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
    checkValidity();
    notifyListeners();
  }

  void addOrRemoveCapability(AppCapability capability) {
    if (selectedCapabilities.contains(capability)) {
      selectedCapabilities.remove(capability);
    } else {
      if (selectedCapabilities.length == 1 && selectedCapabilities.first.id == 'persona') {
        AppSnackbar.showSnackbarError('Other capabilities cannot be selected with Persona');
      } else if (selectedCapabilities.isNotEmpty && capability.id == 'persona') {
        AppSnackbar.showSnackbarError('Persona cannot be selected with other capabilities');
      } else {
        selectedCapabilities.add(capability);
      }
    }
    checkValidity();
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
    checkValidity();
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
    checkValidity();
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
    checkValidity();
    notifyListeners();
  }

  Future<void> generateDescription() async {
    setIsGenratingDescription(true);
    var res = await getGenratedDescription(appNameController.text, appDescriptionController.text);
    appDescriptionController.text = res.decodeString;
    checkValidity();
    setIsGenratingDescription(false);
    notifyListeners();
  }

  void setIsGenratingDescription(bool genrating) {
    isGenratingDescription = genrating;
  }
}
