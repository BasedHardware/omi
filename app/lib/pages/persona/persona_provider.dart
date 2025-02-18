import 'dart:io';
import 'dart:math';

import 'package:flutter/material.dart';
import 'package:friend_private/backend/http/api/apps.dart';
import 'package:friend_private/backend/schema/app.dart';
import 'package:friend_private/utils/alerts/app_snackbar.dart';
import 'package:image_picker/image_picker.dart';

typedef ShowSuccessDialogCallback = void Function(String url);

class PersonaProvider extends ChangeNotifier {
  final GlobalKey<FormState> formKey = GlobalKey<FormState>();
  TextEditingController nameController = TextEditingController();
  TextEditingController usernameController = TextEditingController();
  bool isUsernameTaken = false;
  bool isCheckingUsername = false;
  bool makePersonaPublic = false;
  ShowSuccessDialogCallback? onShowSuccessDialog;

  File? selectedImage;
  String? selectedImageUrl;

  String? personaId;

  bool isFormValid = false;
  bool _isLoading = false;

  Map twitterProfile = {};

  Future getTwitterProfile(String username) async {
    var res = await getTwitterProfileData(username);
    print('Twitter Profile: $res');
    if (res != null) {
      if (res['status'] == 'notfound') {
        AppSnackbar.showSnackbarError('Twitter handle not found');
        twitterProfile = {};
      } else {
        twitterProfile = res;
      }
    }
    notifyListeners();
  }

  Future verifyTweet(String username) async {
    var res = await verifyTwitterOwnership(username);
    if (res) {
      AppSnackbar.showSnackbarSuccess('Twitter handle verified');
    } else {
      AppSnackbar.showSnackbarError('Failed to verify Twitter handle');
    }
    return res;
  }

  void setPersonaPublic(bool? value) {
    if (value == null) {
      return;
    }
    makePersonaPublic = value;
    notifyListeners();
  }

  void prepareUpdatePersona(App app) {
    nameController.text = app.name;
    usernameController.text = app.username!;
    makePersonaPublic = !app.private;
    selectedImageUrl = app.image;
    personaId = app.id;
    notifyListeners();
  }

  Future<void> pickImage() async {
    final ImagePicker picker = ImagePicker();
    final XFile? image = await picker.pickImage(source: ImageSource.gallery);
    if (image != null) {
      selectedImage = File(image.path);
      validateForm();
    }
    notifyListeners();
  }

  void validateForm() {
    isFormValid = formKey.currentState!.validate() && selectedImage != null;
    notifyListeners();
  }

  void resetForm() {
    nameController.clear();
    usernameController.clear();
    selectedImage = null;
    makePersonaPublic = false;
    isFormValid = false;
    onShowSuccessDialog = null;
    notifyListeners();
  }

  Future<void> createPersona() async {
    if (!formKey.currentState!.validate() || selectedImage == null) {
      if (selectedImage == null) {
        AppSnackbar.showSnackbarError('Please select an image');
      }
      return;
    }

    setIsLoading(true);

    try {
      final personaData = {
        'name': nameController.text,
        'username': usernameController.text,
        'private': !makePersonaPublic,
      };

      var res = await createPersonaApp(selectedImage!, personaData);

      if (res) {
        String personaUrl = 'personas.omi.me/u/${usernameController.text}';
        print('Persona URL: $personaUrl');
        if (onShowSuccessDialog != null) {
          onShowSuccessDialog!(personaUrl);
        }
      } else {
        AppSnackbar.showSnackbarError('Failed to create your persona. Please try again later.');
      }
    } catch (e) {
      AppSnackbar.showSnackbarError('Failed to create persona: $e');
    } finally {
      setIsLoading(false);
    }
  }

  Future checkIsUsernameTaken(String username) async {
    setIsCheckingUsername(true);
    isUsernameTaken = await checkPersonaUsername(username);
    setIsCheckingUsername(false);
  }

  void setIsCheckingUsername(bool checking) {
    isCheckingUsername = checking;
    notifyListeners();
  }

  void setIsLoading(bool loading) {
    _isLoading = loading;
    notifyListeners();
  }
}
