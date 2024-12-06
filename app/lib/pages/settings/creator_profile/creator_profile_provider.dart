import 'package:flutter/material.dart';

class CreatorProfileProvider extends ChangeNotifier {
  final TextEditingController creatorNameController = TextEditingController();
  final TextEditingController creatorEmailController = TextEditingController();
  final TextEditingController paypalEmailController = TextEditingController();
  final TextEditingController paypalMeLinkController = TextEditingController();
  final GlobalKey<FormState> formKey = GlobalKey<FormState>();
  bool isFormValid = false;

  void checkValidations() {
    if (formKey.currentState!.validate()) {
      isFormValid = true;
    } else {
      isFormValid = false;
    }
  }
}
