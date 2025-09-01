import 'dart:io';

import 'package:cached_network_image/cached_network_image.dart';
import 'package:collection/collection.dart';
import 'package:file_picker/file_picker.dart';
import 'package:flutter/foundation.dart' hide Category;
import 'package:flutter/cupertino.dart';
import 'package:flutter/material.dart';
import 'package:flutter/services.dart';
import 'package:flutter/widgets.dart';
import 'package:omi/backend/http/api/apps.dart';
import 'package:omi/backend/preferences.dart';
import 'package:omi/backend/schema/app.dart';
import 'package:omi/providers/app_provider.dart';
import 'package:omi/utils/alerts/app_snackbar.dart';
import 'package:omi/widgets/extensions/string.dart';
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
  List<Map<String, dynamic>> actions = [];

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

  // API Keys
  List<AppApiKey> apiKeys = [];
  bool isLoadingApiKeys = false;

  void setAppProvider(AppProvider provider) {
    appProvider = provider;
  }

  Future init({bool presetForConversationAnalysis = false}) async {
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

    // Preset values for conversation analysis template
    if (presetForConversationAnalysis) {
      // Set category to conversation-analysis
      setAppCategory('conversation-analysis');

      // Add memories capability
      final memoriesCapability = capabilities.firstWhereOrNull(
        (cap) => cap.id == 'memories',
      );
      if (memoriesCapability != null && !selectedCapabilities.contains(memoriesCapability)) {
        selectedCapabilities.add(memoriesCapability);
      }

      // Set a helpful default name and description
      appNameController.text = 'My Conversation Analyzer';
      appDescriptionController.text = 'A custom app to analyze and summarize conversations based on my specific needs.';

      checkValidity();
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
      webhookUrlController.text = app.externalIntegration!.webhookUrl ?? '';
      setupCompletedController.text = app.externalIntegration!.setupCompletedUrl ?? '';
      instructionsController.text = app.externalIntegration!.setupInstructionsFilePath ?? '';
      appHomeUrlController.text = app.externalIntegration!.appHomeUrl ?? '';
      if (app.externalIntegration!.authSteps.isNotEmpty) {
        authUrlController.text = app.externalIntegration!.authSteps.first.url;
      }

      // Load actions if they exist
      actions = [];
      if (app.externalIntegration!.actions != null) {
        for (var action in app.externalIntegration!.actions!) {
          actions.add({
            'action': action.action,
          });
        }
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
    actions.clear();
  }

  void addSpecificAction(String actionTypeId) {
    // Check if this action type already exists
    if (!actions.any((action) => action['action'] == actionTypeId)) {
      actions.add({
        'action': actionTypeId,
      });
      checkValidity();
      notifyListeners();
    }
  }

  void removeActionByType(String actionTypeId) {
    actions.removeWhere((action) => action['action'] == actionTypeId);
    checkValidity();
    notifyListeners();
  }

  List<CapacityAction> getActionTypes() {
    for (var capability in capabilities) {
      if (capability.id == 'external_integration') {
        if (capability.actions.isNotEmpty) {
          return capability.actions;
        }
      }
    }

    // Return empty list if no actions found in capabilities
    return [];
  }

  CapacityAction? getActionTypeById(String id) {
    final actionTypes = getActionTypes();
    try {
      return actionTypes.firstWhere((element) => element.id == id);
    } catch (e) {
      return null;
    }
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
            isValid = true;
            if (triggerEvent == null && actions.isEmpty) {
              isValid = false;
            } else if (triggerEvent != null) {
              isValid = true;
              if (externalIntegrationKey.currentState != null) {
                isValid = externalIntegrationKey.currentState!.validate();
              } else {
                isValid = false;
              }
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
            AppSnackbar.showSnackbarError('Please enter a conversation prompt for your app');
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
          // Setup completed URL is optional, so we don't validate it here
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

        // Add actions if they exist
        if (actions.isNotEmpty) {
          data['external_integration']['actions'] = actions;
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

        // Add actions if they exist
        if (actions.isNotEmpty) {
          data['external_integration']['actions'] = actions;
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

  Future pickImage() async {
    try {
      debugPrint('🖼️ Attempting to pick image from gallery...');

      // Use file_picker for desktop platforms, image_picker for mobile
      if (kIsWeb || Platform.isMacOS || Platform.isWindows || Platform.isLinux) {
        debugPrint('🖼️ Using file_picker for desktop platform');
        try {
          FilePickerResult? result = await FilePicker.platform.pickFiles(
            type: FileType.custom,
            allowedExtensions: ['jpg', 'jpeg', 'png', 'gif', 'bmp', 'webp'],
            allowMultiple: false,
            dialogTitle: 'Select an image file',
            withData: false, // Only get file path, not data
            withReadStream: false,
          );

          if (result != null && result.files.isNotEmpty && result.files.single.path != null) {
            debugPrint('🖼️ Image picked successfully via file_picker: ${result.files.single.path}');
            imageFile = File(result.files.single.path!);
            debugPrint('🖼️ Image file set, notifying listeners...');
          } else {
            debugPrint('🖼️ No image selected by user via file_picker');
          }
        } on PlatformException catch (e) {
          debugPrint('🖼️ FilePicker PlatformException: ${e.code} - ${e.message}');
          AppSnackbar.showSnackbarError('Error opening file picker: ${e.message}');
        } catch (e) {
          debugPrint('🖼️ FilePicker general error: $e');
          AppSnackbar.showSnackbarError('Error selecting image: $e');
        }
      } else {
        debugPrint('🖼️ Using image_picker for mobile platform');
        ImagePicker imagePicker = ImagePicker();
        var file = await imagePicker.pickImage(source: ImageSource.gallery);
        if (file != null) {
          debugPrint('🖼️ Image picked successfully via image_picker: ${file.path}');
          imageFile = File(file.path);
          debugPrint('🖼️ Image file set, notifying listeners...');
        } else {
          debugPrint('🖼️ No image selected by user via image_picker');
        }
      }

      notifyListeners();
    } on PlatformException catch (e) {
      debugPrint('🖼️ PlatformException during image picking: ${e.code} - ${e.message}');
      if (e.code == 'photo_access_denied') {
        AppSnackbar.showSnackbarError('Photos permission denied. Please allow access to photos to select an image');
      } else {
        AppSnackbar.showSnackbarError('Error selecting image: ${e.message ?? e.code}');
      }
    } catch (e) {
      debugPrint('🖼️ General exception during image picking: $e');
      AppSnackbar.showSnackbarError('Error selecting image. Please try again.');
    }
    checkValidity();
    notifyListeners();
  }

  Future<void> pickThumbnail() async {
    try {
      debugPrint('🖼️ Attempting to pick thumbnail from gallery...');

      File? thumbnailFile;

      // Use file_picker for desktop platforms, image_picker for mobile
      if (kIsWeb || Platform.isMacOS || Platform.isWindows || Platform.isLinux) {
        debugPrint('🖼️ Using file_picker for desktop platform (thumbnail)');
        try {
          FilePickerResult? result = await FilePicker.platform.pickFiles(
            type: FileType.custom,
            allowedExtensions: ['jpg', 'jpeg', 'png', 'gif', 'bmp', 'webp'],
            allowMultiple: false,
            dialogTitle: 'Select a thumbnail image',
            withData: false,
            withReadStream: false,
          );

          if (result != null && result.files.isNotEmpty && result.files.single.path != null) {
            debugPrint('🖼️ Thumbnail picked successfully via file_picker: ${result.files.single.path}');
            thumbnailFile = File(result.files.single.path!);
          } else {
            debugPrint('🖼️ No thumbnail selected by user via file_picker');
            return;
          }
        } on PlatformException catch (e) {
          debugPrint('🖼️ FilePicker PlatformException (thumbnail): ${e.code} - ${e.message}');
          AppSnackbar.showSnackbarError('Error opening file picker: ${e.message}');
          return;
        } catch (e) {
          debugPrint('🖼️ FilePicker general error (thumbnail): $e');
          AppSnackbar.showSnackbarError('Error selecting thumbnail: $e');
          return;
        }
      } else {
        debugPrint('🖼️ Using image_picker for mobile platform (thumbnail)');
        ImagePicker imagePicker = ImagePicker();
        var file = await imagePicker.pickImage(
          source: ImageSource.gallery,
          imageQuality: 85,
        );
        if (file != null) {
          debugPrint('🖼️ Thumbnail picked successfully via image_picker: ${file.path}');
          thumbnailFile = File(file.path);
        } else {
          debugPrint('🖼️ No thumbnail selected by user via image_picker');
          return;
        }
      }

      if (thumbnailFile != null) {
        setIsUploadingThumbnail(true);

        // Upload thumbnail
        debugPrint('🖼️ Uploading thumbnail...');
        var result = await uploadAppThumbnail(thumbnailFile);
        if (result.isNotEmpty) {
          thumbnailUrls.add(result['thumbnail_url']!);
          thumbnailIds.add(result['thumbnail_id']!);
          debugPrint('🖼️ Thumbnail uploaded successfully');
        }
        setIsUploadingThumbnail(false);
      }
    } on PlatformException catch (e) {
      debugPrint('🖼️ PlatformException during thumbnail picking: ${e.code} - ${e.message}');
      if (e.code == 'photo_access_denied') {
        AppSnackbar.showSnackbarError('Photos permission denied. Please allow access to photos to select an image');
      } else {
        AppSnackbar.showSnackbarError('Error selecting thumbnail: ${e.message ?? e.code}');
      }
      setIsUploadingThumbnail(false);
    } catch (e) {
      debugPrint('🖼️ General exception during thumbnail picking: $e');
      AppSnackbar.showSnackbarError('Error selecting thumbnail. Please try again.');
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

  Future updateImage() async {
    try {
      // Use file_picker for desktop platforms, image_picker for mobile
      if (kIsWeb || Platform.isMacOS || Platform.isWindows || Platform.isLinux) {
        FilePickerResult? result = await FilePicker.platform.pickFiles(
          type: FileType.custom,
          allowedExtensions: ['jpg', 'jpeg', 'png', 'gif', 'bmp', 'webp'],
          allowMultiple: false,
          dialogTitle: 'Select an image file',
          withData: false,
          withReadStream: false,
        );

        if (result != null && result.files.isNotEmpty && result.files.single.path != null) {
          imageFile = File(result.files.single.path!);
          if (imageUrl != null) {
            await CachedNetworkImage.evictFromCache(imageUrl!, cacheKey: imageUrl);
          }
          imageUrl = null;
        }
      } else {
        ImagePicker imagePicker = ImagePicker();
        var file = await imagePicker.pickImage(source: ImageSource.gallery);
        if (file != null) {
          imageFile = File(file.path);
          if (imageUrl != null) {
            await CachedNetworkImage.evictFromCache(imageUrl!, cacheKey: imageUrl);
          }
          imageUrl = null;
        }
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
    // Allow setting to null to clear the selection
    triggerEvent = event;
    checkValidity();
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

  // API Keys methods
  Future<void> loadApiKeys(String appId) async {
    isLoadingApiKeys = true;
    notifyListeners();

    try {
      apiKeys = await listApiKeysServer(appId);
    } catch (e) {
      print('Error loading provider API keys: $e');
    } finally {
      isLoadingApiKeys = false;
      notifyListeners();
    }
  }

  Future<AppApiKey> createApiKey(String appId) async {
    final result = await createApiKeyServer(appId);
    await loadApiKeys(appId);
    return AppApiKey.fromJson(result);
  }

  Future<void> deleteApiKey(String appId, String keyId) async {
    await deleteApiKeyServer(appId, keyId);
    await loadApiKeys(appId);
  }
}
