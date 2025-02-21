import 'dart:io';

import 'package:flutter/material.dart';
import 'package:friend_private/backend/http/api/apps.dart';
import 'package:friend_private/backend/preferences.dart';
import 'package:friend_private/backend/schema/app.dart';
import 'package:friend_private/utils/alerts/app_snackbar.dart';
import 'package:image_picker/image_picker.dart';

typedef ShowSuccessDialogCallback = void Function(String url);

class PersonaProvider extends ChangeNotifier {
  final GlobalKey<FormState> formKey = GlobalKey<FormState>();
  TextEditingController nameController = TextEditingController(text: SharedPreferencesUtil().givenName);
  TextEditingController usernameController = TextEditingController();
  bool isUsernameTaken = false;
  bool isCheckingUsername = false;
  bool makePersonaPublic = false;
  ShowSuccessDialogCallback? onShowSuccessDialog;

  File? selectedImage;
  String? selectedImageUrl;

  String? personaId;

  bool isFormValid = true;
  bool isLoading = false;

  Map twitterProfile = {};
  App? userPersona;

  String username = '';

  void updateUsername(String value) {
    username = value;
    notifyListeners();
  }

  Future getTwitterProfile(String handle) async {
    setIsLoading(true);
    var res = await getTwitterProfileData(handle);
    print('Twitter Profile: $res');
    if (res != null) {
      if (res['status'] == 'notfound') {
        AppSnackbar.showSnackbarError('Twitter handle not found');
        twitterProfile = {};
      } else {
        twitterProfile = res;
      }
    }
    setIsLoading(false);
    notifyListeners();
  }

  Future verifyTweet() async {
    var res = await verifyTwitterOwnership(username, twitterProfile['profile'], personaId);
    if (!res) {
      AppSnackbar.showSnackbarError('Failed to verify Twitter handle');
    }
    return res;
  }

  Future getUserPersona() async {
    setIsLoading(true);
    var res = await getUserPersonaServer();
    if (res != null) {
      userPersona = res;
    } else {
      userPersona = null;
      AppSnackbar.showSnackbarError('Failed to fetch your persona');
    }
    setIsLoading(false);
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
    isFormValid = formKey.currentState!.validate() && (selectedImage != null || selectedImageUrl != null);
    notifyListeners();
  }

  void resetForm() {
    nameController.clear();
    usernameController.clear();
    selectedImage = null;
    makePersonaPublic = false;
    isFormValid = false;
    onShowSuccessDialog = null;
    personaId = null;
    twitterProfile = {};
    notifyListeners();
  }

  Future<void> updatePersona() async {
    if (!formKey.currentState!.validate()) {
      if (selectedImage == null && selectedImageUrl == null) {
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
        'id': personaId,
      };

      var res = await updatePersonaApp(selectedImage, personaData);

      if (res) {
        AppSnackbar.showSnackbarSuccess('Persona updated successfully');
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
        'private': !makePersonaPublic,
        'username': username,
      };

      if (twitterProfile.isNotEmpty) {
        personaData['connected_accounts'] = ['omi', 'twitter'];
        personaData['twitter'] = {
          'username': twitterProfile['profile'],
          'avatar': twitterProfile['avatar'],
        };
      }

      var res = await createPersonaApp(selectedImage!, personaData);

      if (res.isNotEmpty) {
        String personaUrl = 'personas.omi.me/u/${res['username']}';
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
    isLoading = loading;
    notifyListeners();
  }

  Future<bool> enablePersonaApp() async {
    setIsLoading(true);
    if (userPersona == null) {
      await getUserPersona();
    }
    try {
      var enabled = await enableAppServer(userPersona!.id);
      if (enabled) {
        return true;
      } else {
        AppSnackbar.showSnackbarError('Failed to enable persona');
        return false;
      }
    } catch (e) {
      AppSnackbar.showSnackbarError('Error enabling persona: $e');
      return false;
    } finally {
      setIsLoading(false);
    }
  }
}
