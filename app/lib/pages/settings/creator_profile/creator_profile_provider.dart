import 'dart:async';

import 'package:flutter/material.dart';
import 'package:friend_private/backend/http/api/users.dart';
import 'package:friend_private/backend/schema/profile.dart';
import 'package:friend_private/utils/alerts/app_snackbar.dart';

class CreatorProfileProvider extends ChangeNotifier {
  final TextEditingController creatorNameController = TextEditingController();
  final TextEditingController creatorEmailController = TextEditingController();
  final TextEditingController paypalEmailController = TextEditingController();
  final TextEditingController paypalMeLinkController = TextEditingController();
  final GlobalKey<FormState> formKey = GlobalKey<FormState>();
  bool showSubmitButton = false;
  bool isLoading = false;
  bool profileExists = false;

  void setIsLoading(bool value) {
    isLoading = value;
    notifyListeners();
  }

  void submitButtonStatus() {
    if (creatorNameController.text.isNotEmpty &&
        creatorEmailController.text.isNotEmpty &&
        paypalEmailController.text.isNotEmpty &&
        paypalMeLinkController.text.isNotEmpty) {
      showSubmitButton = true;
    } else {
      showSubmitButton = false;
    }
    notifyListeners();
  }

  Future<void> getCreatorProfileDetails() async {
    var res = await getCreatorProfile();
    if (res != null) {
      if (res.isEmpty()) {
        AppSnackbar.showSnackbarInfo('Looks like you have not created your Creator Profile yet');
      } else {
        profileExists = true;
        creatorNameController.text = res.creatorName;
        creatorEmailController.text = res.creatorEmail;
        paypalEmailController.text = res.paypalEmail;
        paypalMeLinkController.text = res.paypalMeLink ?? '';
      }
      showSubmitButton = false;
    } else {
      AppSnackbar.showSnackbarError('Failed to fetch your Creator Profile details');
    }
  }

  Future updateDetails() async {
    if (formKey.currentState!.validate()) {
      setIsLoading(true);
      var res = await updateCreatorProfileServer(
        creatorNameController.text,
        creatorEmailController.text,
        paypalEmailController.text,
        paypalMeLinkController.text,
      );
      if (res) {
        AppSnackbar.showSnackbarSuccess('Creator Profile updated successfully');
      } else {
        AppSnackbar.showSnackbarError('Failed to update Creator Profile');
      }
      showSubmitButton = false;
      setIsLoading(false);
    } else {
      AppSnackbar.showSnackbarError('Please fill all the fields correctly');
    }
  }

  Future saveDetails() async {
    if (formKey.currentState!.validate()) {
      setIsLoading(true);
      var profile = CreatorProfile(
        creatorName: creatorNameController.text,
        creatorEmail: creatorEmailController.text,
        paypalEmail: paypalEmailController.text,
        paypalMeLink: paypalMeLinkController.text,
        isVerified: false,
      );
      var res = await saveCreatorProfile(profile);
      if (res) {
        profileExists = true;
        AppSnackbar.showSnackbarSuccess('Creator Profile saved successfully');
      } else {
        AppSnackbar.showSnackbarError('Failed to update Creator Profile');
      }
      showSubmitButton = false;
      setIsLoading(false);
    } else {
      AppSnackbar.showSnackbarError('Please fill all the fields correctly');
    }
  }
}
