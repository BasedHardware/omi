import 'dart:io';

import 'package:flutter/foundation.dart';
import 'package:flutter/material.dart';
import 'package:friend_private/backend/preferences.dart';
import 'package:image_picker/image_picker.dart';

class AddAppProvider extends ChangeNotifier {
  TextEditingController appNameController = TextEditingController();
  TextEditingController appDescriptionController = TextEditingController();
  TextEditingController creatorNameController = TextEditingController();
  TextEditingController creatorEmailController = TextEditingController();
  TextEditingController chatPromptController = TextEditingController();
  TextEditingController memoryPromptController = TextEditingController();
  File? imageFile;
  List<String> capabilities = [];

  void init() {
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
}
