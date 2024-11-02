import 'dart:io';

import 'package:flutter/material.dart';
import 'package:flutter/widgets.dart';
import 'package:friend_private/backend/preferences.dart';
import 'package:friend_private/utils/alerts/app_snackbar.dart';
import 'package:image_picker/image_picker.dart';

class AddAppProvider extends ChangeNotifier {
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

  String? privacyLevel;
  bool termsAgreed = false;

  List<String> categories = [];

  File? imageFile;
  List<String> capabilities = [];

  void init() {
    getCategories();
    creatorNameController.text = SharedPreferencesUtil().givenName;
    creatorEmailController.text = SharedPreferencesUtil().email;
  }

  void clear() {
    appNameController.clear();
    appDescriptionController.clear();
    creatorNameController.clear();
    creatorEmailController.clear();
    chatPromptController.clear();
    memoryPromptController.clear();
  }

  void getCategories() {
    // TODO: Fetch categories from the backend
    categories = [
      'Conversation Analysis',
      'Personality Emulation',
      'Health and Wellness',
      'Education and Learning',
      'Emotional and Mental Support',
    ];
    notifyListeners();
  }

  void submitApp() {
    if (formKey.currentState!.validate()) {
      if (!termsAgreed) {
        AppSnackbar.showSnackbarError('Please agree to the terms and conditions to proceed');
        return;
      }
      if (!capabilitySelected()) {
        AppSnackbar.showSnackbarError('Please select at least one capability for your app');
        return;
      }
    } else {
      AppSnackbar.showSnackbarError('Please fill in all the required fields correctly');
    }
  }

  Future pickImage() async {
    ImagePicker imagePicker = ImagePicker();
    var file = await imagePicker.pickImage(source: ImageSource.gallery);
    if (file != null) {
      imageFile = File(file.path);
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

  void setPrivacyLevel(String? level) {
    if (level == null) {
      return;
    }
    privacyLevel = level;
    notifyListeners();
  }

  void setTermsAgreed(bool? agreed) {
    if (agreed == null) {
      return;
    }
    termsAgreed = agreed;
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
