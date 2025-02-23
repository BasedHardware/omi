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
  bool isFormValid = false;
  bool hasOmiConnection = false;
  bool hasTwitterConnection = false;
  ShowSuccessDialogCallback? onShowSuccessDialog;

  File? selectedImage;
  String? selectedImageUrl;

  String? personaId;

  String? get _verifiedPersonaId => SharedPreferencesUtil().verifiedPersonaId;

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
    debugPrint('Twitter Profile: $res');
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
    var (verified, verifiedPersonaId) = await verifyTwitterOwnership(username, twitterProfile['profile'], personaId);
    if (!verified) {
      AppSnackbar.showSnackbarError('Failed to verify Twitter handle');
    }
    SharedPreferencesUtil().hasPersonaCreated = true;
    SharedPreferencesUtil().verifiedPersonaId = verifiedPersonaId;
    toggleTwitterConnection(true);

    return verified;
  }

  // TODO: get rid of this one
  Future _getUserPersona() async {
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

  Future getVerifiedUserPersona() async {
    if (_verifiedPersonaId == null) {
      return;
    }
    setIsLoading(true);

    // Warn: improvement needed
    var res = await getAppDetailsServer(_verifiedPersonaId!);
    if (res != null) {
      userPersona = App.fromJson(res);
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
    userPersona = app;
    hasOmiConnection = app.connectedAccounts.contains('omi');
    hasTwitterConnection = app.connectedAccounts.contains('twitter');
    if (hasTwitterConnection && app.twitter != null) {
      twitterProfile = app.twitter!;
    }
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
    bool hasValidImage = selectedImage != null || selectedImageUrl != null;
    bool hasValidFormFields = formKey.currentState!.validate();
    bool hasKnowledgeData = hasOmiConnection || hasTwitterConnection;

    isFormValid = hasValidImage && hasValidFormFields && hasKnowledgeData;
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
    hasOmiConnection = false;
    userPersona = null;
    hasTwitterConnection = false;
    twitterProfile = {};
    notifyListeners();
  }

  void toggleOmiConnection(bool value) {
    hasOmiConnection = value;
    notifyListeners();
  }

  void toggleTwitterConnection(bool value) {
    hasTwitterConnection = value;
    if (!value) {
      twitterProfile = {};
    }
    notifyListeners();
  }

  void disconnectTwitter() {
    twitterProfile = {};
    hasTwitterConnection = false;
    notifyListeners();
  }

  void disconnectOmi() {
    hasOmiConnection = false;
    notifyListeners();
  }

  Future<void> updatePersona() async {
    if (!hasOmiConnection && !hasTwitterConnection) {
      AppSnackbar.showSnackbarError('Please connect at least one knowledge data source (Omi or Twitter)');
      return;
    }

    setIsLoading(true);
    try {
      Map<String, dynamic> personaData = {
        'id': userPersona!.id,
        'name': nameController.text,
        'username': usernameController.text,
        'private': !makePersonaPublic,
      };

      if (hasOmiConnection && !userPersona!.connectedAccounts.contains('omi')) {
        personaData['connected_accounts'] = [...userPersona!.connectedAccounts, 'omi'];
      } else if (!hasOmiConnection && userPersona!.connectedAccounts.contains('omi')) {
        personaData['connected_accounts'] =
            userPersona!.connectedAccounts.where((element) => element != 'omi').toList();
      }

      if (hasTwitterConnection && !userPersona!.connectedAccounts.contains('twitter')) {
        personaData['connected_accounts'] = [...userPersona!.connectedAccounts, 'twitter'];
        personaData['twitter'] = {
          'username': twitterProfile['profile'],
          'avatar': twitterProfile['avatar'],
        };
      } else if (!hasTwitterConnection && userPersona!.connectedAccounts.contains('twitter')) {
        personaData['connected_accounts'] =
            userPersona!.connectedAccounts.where((element) => element != 'twitter').toList();
      }

      bool success = await updatePersonaApp(selectedImage, personaData);
      if (success) {
        AppSnackbar.showSnackbarSuccess('Persona updated successfully');
        await getVerifiedUserPersona();
        notifyListeners();
      } else {
        AppSnackbar.showSnackbarError('Failed to update persona');
      }
    } catch (e) {
      print('Error updating persona: $e');
      AppSnackbar.showSnackbarError('Failed to update persona');
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

    if (!hasOmiConnection && !hasTwitterConnection) {
      AppSnackbar.showSnackbarError('Please connect at least one knowledge data source (Omi or Twitter)');
      return;
    }

    setIsLoading(true);

    try {
      final personaData = {
        'name': nameController.text,
        'private': !makePersonaPublic,
        'username': username,
        'connected_accounts': <String>[],
      };

      if (hasOmiConnection) {
        (personaData['connected_accounts'] as List<String>).add('omi');
      }

      if (twitterProfile.isNotEmpty) {
        (personaData['connected_accounts'] as List<String>).add('twitter');
        personaData['twitter'] = {
          'username': twitterProfile['profile'],
          'avatar': twitterProfile['avatar'],
        };
      }

      var res = await createPersonaApp(selectedImage!, personaData);

      if (res.isNotEmpty) {
        String personaUrl = 'personas.omi.me/u/${res['username']}';
        debugPrint('Persona URL: $personaUrl');
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
      await getVerifiedUserPersona();
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
