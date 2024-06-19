import 'package:flutter/material.dart';
import 'package:friend_private/backend/preferences.dart';
import 'package:gradient_borders/box_borders/gradient_box_border.dart';

class BackupPasswordPage extends StatefulWidget {
  const BackupPasswordPage({super.key});

  @override
  State<BackupPasswordPage> createState() => _BackupPasswordPageState();
}

class _BackupPasswordPageState extends State<BackupPasswordPage> {
  TextEditingController currentPasswordController = TextEditingController();
  TextEditingController newPasswordController = TextEditingController();
  TextEditingController repeatPasswordController = TextEditingController();

  bool backupsEnabled = false;
  bool hasPasswordSet = false;

  @override
  void initState() {
    backupsEnabled = SharedPreferencesUtil().backupsEnabled;
    hasPasswordSet = SharedPreferencesUtil().hasBackupPassword;
    setState(() {});
    super.initState();
  }

  @override
  Widget build(BuildContext context) {
    return GestureDetector(
      onTap: () => FocusScope.of(context).unfocus(),
      child: Scaffold(
        appBar: AppBar(
          title: const Text('Backups Password'),
          backgroundColor: Theme.of(context).colorScheme.primary,
        ),
        backgroundColor: Theme.of(context).colorScheme.primary,
        body: ListView(
          children: [
            // if current password
            const SizedBox(height: 32),
            hasPasswordSet
                ? _getTextField(
                    currentPasswordController,
                    hintText: 'Current password',
                  )
                : Container(),
            // password
            hasPasswordSet ? const SizedBox(height: 12) : Container(),
            hasPasswordSet
                ? Padding(
                    padding: const EdgeInsets.all(16.0),
                    child: Container(
                      height: 1,
                      color: Colors.grey.shade900,
                      width: double.maxFinite,
                    ),
                  )
                : Container(),
            hasPasswordSet ? const SizedBox(height: 16) : Container(),
            hasPasswordSet
                ? const Padding(
                    padding: EdgeInsets.symmetric(horizontal: 24),
                    child: Text(
                      'New password',
                      style: TextStyle(
                        color: Colors.white,
                        fontSize: 18,
                      ),
                    ),
                  )
                : Container(),
            const SizedBox(height: 32),
            _getTextField(newPasswordController, hintText: 'New password'),
            const SizedBox(height: 24),
            // repeat password
            _getTextField(repeatPasswordController, hintText: 'Repeat new password'),
            const SizedBox(height: 40),
            Center(
              child: MaterialButton(
                padding: const EdgeInsets.symmetric(horizontal: 32, vertical: 16),
                onPressed: setPassword,
                shape: RoundedRectangleBorder(
                  borderRadius: BorderRadius.circular(8),
                  side: const BorderSide(color: Colors.white, width: 1),
                ),
                child: const Text('SET NEW PASSWORD'),
              ),
            )
          ],
        ),
      ),
    );
  }

  setPassword() {
    if (newPasswordController.text.isEmpty || repeatPasswordController.text.isEmpty) {
      return;
    }
    if (hasPasswordSet && currentPasswordController.text != SharedPreferencesUtil().backupPassword) {
      ScaffoldMessenger.of(context).showSnackBar(const SnackBar(content: Text('Current password is incorrect')));
      return;
    }
    if (newPasswordController.text != repeatPasswordController.text) {
      ScaffoldMessenger.of(context).showSnackBar(const SnackBar(content: Text('Passwords do not match')));
      return;
    }
    SharedPreferencesUtil().backupPassword = newPasswordController.text;
    hasPasswordSet = true;
    ScaffoldMessenger.of(context).showSnackBar(const SnackBar(content: Text('Password Reset')));
    Navigator.of(context).pop();
  }

  _getTextField(TextEditingController controller, {String hintText = ''}) {
    return Container(
      width: double.maxFinite,
      padding: const EdgeInsets.fromLTRB(16, 4, 16, 4),
      margin: const EdgeInsets.fromLTRB(18, 0, 18, 0),
      decoration: const BoxDecoration(
        color: Colors.black,
        borderRadius: BorderRadius.all(Radius.circular(16)),
        border: GradientBoxBorder(
          gradient: LinearGradient(colors: [
            Color.fromARGB(127, 208, 208, 208),
            Color.fromARGB(127, 188, 99, 121),
            Color.fromARGB(127, 86, 101, 182),
            Color.fromARGB(127, 126, 190, 236)
          ]),
          width: 1,
        ),
        shape: BoxShape.rectangle,
      ),
      child: TextField(
        enabled: true,
        controller: controller,
        obscureText: true,
        decoration: InputDecoration(
          hintText: hintText,
          hintStyle: const TextStyle(fontSize: 14.0, color: Colors.grey),
          enabledBorder: InputBorder.none,
          focusedBorder: InputBorder.none,
        ),
        // maxLines: 8,
        // minLines: 1,
        // keyboardType: TextInputType.multiline,
        style: TextStyle(fontSize: 14.0, color: Colors.grey.shade200),
      ),
    );
  }
}
