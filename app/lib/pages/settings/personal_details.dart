import 'package:firebase_auth/firebase_auth.dart';
import 'package:flutter/material.dart';
import 'package:friend_private/backend/auth.dart';
import 'package:friend_private/utils/alerts/app_snackbar.dart';
import 'package:gradient_borders/gradient_borders.dart';

class PersonalDetails extends StatefulWidget {
  const PersonalDetails({super.key});

  @override
  State<PersonalDetails> createState() => _PersonalDetailsState();
}

class _PersonalDetailsState extends State<PersonalDetails> {
  late TextEditingController nameController;
  User? user;
  bool isSaving = false;

  @override
  void initState() {
    user = getFirebaseUser();
    nameController = TextEditingController(text: user?.displayName ?? '');
    super.initState();
  }

  @override
  Widget build(BuildContext context) {
    return Scaffold(
      backgroundColor: Theme.of(context).colorScheme.primary,
      appBar: AppBar(
        backgroundColor: Theme.of(context).colorScheme.primary,
        actions: [
          MaterialButton(
            onPressed: () async {
              if (nameController.text.isEmpty || nameController.text.trim().isEmpty) {
                AppSnackbar.showSnackbarError('Name cannot be empty');
                return;
              }
              setState(() {
                isSaving = true;
              });
              await updateGivenName(nameController.text);
              setState(() {
                isSaving = false;
              });
              AppSnackbar.showSnackbar(
                'Name updated successfully!',
              );
              Navigator.of(context).pop();
            },
            color: Colors.transparent,
            elevation: 0,
            child: isSaving
                ? const Center(
                    child: Padding(
                      padding: EdgeInsets.all(8.0),
                      child: CircularProgressIndicator(
                        color: Colors.white,
                      ),
                    ),
                  )
                : const Padding(
                    padding: EdgeInsets.symmetric(horizontal: 4.0),
                    child: Text(
                      'Save',
                      style: TextStyle(color: Colors.deepPurple, fontWeight: FontWeight.w600, fontSize: 16),
                    ),
                  ),
          )
        ],
      ),
      body: Padding(
        padding: const EdgeInsets.only(left: 18, right: 18),
        child: Column(
          crossAxisAlignment: CrossAxisAlignment.start,
          children: [
            const SizedBox(
              height: 30,
            ),
            TextFormField(
              enabled: true,
              controller: nameController,
              // textCapitalization: TextCapitalization.sentences,
              obscureText: false,
              // canRequestFocus: true,
              textAlign: TextAlign.start,
              textAlignVertical: TextAlignVertical.center,
              decoration: InputDecoration(
                hintText: 'Enter your full name',
                hintStyle: const TextStyle(fontSize: 14.0, color: Colors.grey),
                floatingLabelBehavior: FloatingLabelBehavior.always,
                label: Text(
                  'Given Name',
                  style: TextStyle(
                    color: Colors.grey.shade200,
                    fontSize: 16,
                  ),
                ),
                border: GradientOutlineInputBorder(
                  borderRadius: BorderRadius.circular(8),
                  gradient: const LinearGradient(
                    colors: <Color>[
                      Color.fromARGB(255, 202, 201, 201),
                      Color.fromARGB(255, 159, 158, 158),
                    ],
                  ),
                ),
              ),
              style: TextStyle(fontSize: 14.0, color: Colors.grey.shade200),
            ),
            const SizedBox(
              height: 30,
            ),
            // TextFormField(
            //   enabled: true,
            //   obscureText: false,
            //   textAlign: TextAlign.start,
            //   textAlignVertical: TextAlignVertical.center,
            //   readOnly: true,
            //   initialValue: user?.email,
            //   decoration: InputDecoration(
            //     floatingLabelBehavior: FloatingLabelBehavior.always,
            //     label: Text(
            //       'Email Address',
            //       style: TextStyle(
            //         color: Colors.grey.shade200,
            //         fontSize: 16,
            //       ),
            //     ),
            //     border: GradientOutlineInputBorder(
            //       borderRadius: BorderRadius.circular(8),
            //       gradient: const LinearGradient(
            //         colors: <Color>[
            //           Color.fromARGB(255, 202, 201, 201),
            //           Color.fromARGB(255, 159, 158, 158),
            //         ],
            //       ),
            //     ),
            //   ),
            //   style: TextStyle(fontSize: 14.0, color: Colors.grey.shade200),
            // ),
          ],
        ),
      ),
    );
  }
}
