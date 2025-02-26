import 'dart:io';

import 'package:flutter/material.dart';
import 'package:friend_private/backend/http/api/apps.dart';
import 'package:friend_private/backend/preferences.dart';
import 'package:friend_private/backend/schema/app.dart';
import 'package:friend_private/utils/alerts/app_snackbar.dart';
import 'package:image_picker/image_picker.dart';

typedef ShowSuccessDialogCallback = void Function(String url);

enum PersonaProfileRouting {
  no_device,
  create_my_clone,
  apps_updates,
  home,
}

class PersonaProvider extends ChangeNotifier {
  // Routing state for persona profile
  PersonaProfileRouting _routing = PersonaProfileRouting.no_device;
  PersonaProfileRouting get routing => _routing;

  void setRouting(PersonaProfileRouting routing, {App? app}) {
    _routing = routing;
    if (app != null) {
      _userPersona = app;
      prepareUpdatePersona(app);
    }
    notifyListeners();
  }

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

  Future updatePersonaName() async {
    debugPrint("updatePersonaName");
    await updatePersona();
    notifyListeners();
  }

  String? get _verifiedPersonaId => SharedPreferencesUtil().verifiedPersonaId;

  bool isLoading = false;

  Map _twitterProfile = {};
  Map get twitterProfile => _twitterProfile;

  App? _userPersona;
  App? get userPersona => _userPersona;
  String? get personaId => _userPersona?.id;

  String _username = '';
  String get username => _username;

  void updateUsername(String value) {
    _username = value;
    notifyListeners();
  }

  Future getTwitterProfile(String handle) async {
    setIsLoading(true);
    var res = await getTwitterProfileData(handle);
    debugPrint('Twitter Profile: $res');
    if (res != null) {
      if (res['status'] == 'notfound') {
        AppSnackbar.showSnackbarError('Twitter handle not found');
        _twitterProfile = {};
      } else {
        _twitterProfile = res;
      }
    }
    setIsLoading(false);
    notifyListeners();
  }

  Future verifyTweet() async {
    var (verified, verifiedPersonaId) = await verifyTwitterOwnership(_username, _twitterProfile['profile'], personaId);
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
      _userPersona = res;
    } else {
      _userPersona = null;
      AppSnackbar.showSnackbarError('Failed to fetch your persona');
    }
    setIsLoading(false);
  }

  // Get upsert verified user persona
  Future getVerifiedUserPersona() async {
    setIsLoading(true);

    if (_verifiedPersonaId == null || routing != PersonaProfileRouting.no_device) {
      // If no verified persona ID exists, get or create one
      var res = await getUpsertUserPersonaServer();
      if (res != null) {
        _userPersona = App.fromJson(res);
        // Save the persona ID for future use
        SharedPreferencesUtil().verifiedPersonaId = _userPersona?.id;
      } else {
        _userPersona = null;
        AppSnackbar.showSnackbarError('Failed to create your persona');
      }
    } else {
      // If we have a verified persona ID, fetch it
      var res = await getAppDetailsServer(_verifiedPersonaId!);
      if (res != null) {
        _userPersona = App.fromJson(res);
      } else {
        _userPersona = null;
        AppSnackbar.showSnackbarError('Failed to fetch your persona');
      }
    }

    // Prepare for updates
    if (_userPersona != null) {
      prepareUpdatePersona(_userPersona!);
    }

    setIsLoading(false);
  }

  void setPersonaPublic(bool? value) {
    if (value == null) {
      return;
    }
    if (value == makePersonaPublic) {
      return;
    }
    makePersonaPublic = value;

    // Update
    debugPrint("setPersonaPublic");
    updatePersona();
  }

  void prepareUpdatePersona(App app) {
    nameController.text = app.name;
    usernameController.text = app.username!;
    makePersonaPublic = !app.private;
    selectedImageUrl = app.image;
    _userPersona = app;
    hasOmiConnection = app.connectedAccounts.contains('omi');
    hasTwitterConnection = app.connectedAccounts.contains('twitter');
    if (hasTwitterConnection && app.twitter != null) {
      _twitterProfile = app.twitter!;
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

  Future<void> pickAndUpdateImage() async {
    final ImagePicker picker = ImagePicker();
    final XFile? image = await picker.pickImage(source: ImageSource.gallery);
    if (image != null) {
      selectedImage = File(image.path);
      validateForm();

      // Update
      debugPrint("pickAndUpdateImage");
      await updatePersona();
    }
    notifyListeners();
  }

  void validateForm() {
    bool hasValidImage = selectedImage != null || selectedImageUrl != null;
    bool hasValidFormFields = true; //formKey.currentState!.validate(); // dont use form for now
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
    hasOmiConnection = false;
    _userPersona = null;
    hasTwitterConnection = false;
    _twitterProfile = {};
    notifyListeners();
  }

  void toggleOmiConnection(bool value) {
    hasOmiConnection = value;
    notifyListeners();
  }

  void toggleTwitterConnection(bool value) {
    hasTwitterConnection = value;
    if (!value) {
      _twitterProfile = {};
    }
    notifyListeners();
  }

  void disconnectTwitter() {
    _twitterProfile = {};
    hasTwitterConnection = false;

    debugPrint("disconnectTwitter");
    if (_isEditablePersona()) {
      updatePersona();
    }
    notifyListeners();
  }

  void disconnectOmi() {
    hasOmiConnection = false;
    debugPrint("disconnectOmi");
    if (_isEditablePersona()) {
      updatePersona();
    }
    notifyListeners();
  }

  bool _isEditablePersona() {
    return routing != PersonaProfileRouting.no_device;
  }

  Future<void> updatePersona() async {
    if (!hasOmiConnection && !hasTwitterConnection) {
      AppSnackbar.showSnackbarError('Please connect at least one knowledge data source (Omi or Twitter)');
      return;
    }

    setIsLoading(true);
    try {
      Map<String, dynamic> personaData = {
        'id': _userPersona!.id,
        'name': nameController.text,
        'username': usernameController.text,
        'private': !makePersonaPublic,
      };

      // Fix hasOmiConnection
      if (!hasOmiConnection && _userPersona?.uid == SharedPreferencesUtil().uid) {
        hasOmiConnection = true;
      }

      if (hasOmiConnection && !_userPersona!.connectedAccounts.contains('omi')) {
        personaData['connected_accounts'] = [..._userPersona!.connectedAccounts, 'omi'];
      } else if (!hasOmiConnection && _userPersona!.connectedAccounts.contains('omi')) {
        personaData['connected_accounts'] =
            _userPersona!.connectedAccounts.where((element) => element != 'omi').toList();
      }

      if (hasTwitterConnection && !_userPersona!.connectedAccounts.contains('twitter')) {
        personaData['connected_accounts'] = [..._userPersona!.connectedAccounts, 'twitter'];
        personaData['twitter'] = {
          'username': _twitterProfile['profile'],
          'avatar': _twitterProfile['avatar'],
        };
      } else if (!hasTwitterConnection && _userPersona!.connectedAccounts.contains('twitter')) {
        personaData['connected_accounts'] =
            _userPersona!.connectedAccounts.where((element) => element != 'twitter').toList();
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
        'username': _username,
        'connected_accounts': <String>[],
      };

      if (hasOmiConnection) {
        (personaData['connected_accounts'] as List<String>).add('omi');
      }

      if (_twitterProfile.isNotEmpty) {
        (personaData['connected_accounts'] as List<String>).add('twitter');
        personaData['twitter'] = {
          'username': _twitterProfile['profile'],
          'avatar': _twitterProfile['avatar'],
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
    if (_userPersona == null) {
      await getVerifiedUserPersona();
    }
    try {
      var enabled = await enableAppServer(_userPersona!.id);
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

  Future onTwitterVerifiedCompleted() async {
    debugPrint("routing ${routing}");
    if (routing == PersonaProfileRouting.no_device) {
      return;
    }

    // update
    debugPrint("onTwitterVerifiedCompleted");
    updatePersona();
  }
}
