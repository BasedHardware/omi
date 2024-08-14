import 'package:flutter/material.dart';
import 'package:friend_private/backend/mixpanel.dart';
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

  bool obscureCurrentPassword = true;
  bool obscureNewPassword = true;
  bool obscureRepeatPassword = true;

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
                    obscureText: obscureCurrentPassword,
                    onVisibilityChanged: () {
                      setState(() {
                        obscureCurrentPassword = !obscureCurrentPassword;
                      });
                    },
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
                      'New Password',
                      style: TextStyle(
                        color: Colors.white,
                        fontSize: 18,
                      ),
                    ),
                  )
                : Container(),
            const SizedBox(height: 32),
            _getTextField(
              newPasswordController,
              hintText: 'New password',
              obscureText: obscureNewPassword,
              onVisibilityChanged: () {
                setState(() {
                  obscureNewPassword = !obscureNewPassword;
                });
              },
            ),
            const SizedBox(height: 24),
            // repeat password
            _getTextField(repeatPasswordController, hintText: 'Repeat new password', obscureText: obscureRepeatPassword,
                onVisibilityChanged: () {
              setState(() {
                obscureRepeatPassword = !obscureRepeatPassword;
              });
            }),
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
            ),
            const SizedBox(height: 32),
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
      _snackBar('Current password is incorrect  👀');
      return;
    }
    if (newPasswordController.text != repeatPasswordController.text) {
      _snackBar('Passwords do not match   😕');
      return;
    }
    var newPassword = newPasswordController.text;
    if (newPassword.length < 8) {
      _snackBar('Password must be at least 8 characters long   🔐', seconds: 2);
      return;
    }
    // regex for password strength, 8 characters, 1 number, 1 special char
    if (!RegExp(r'^(?=.*[0-9])(?=.*[!@#\$%\^&\*])(?=.{8,})').hasMatch(newPassword)) {
      _snackBar('Password must contain at least 1 number and 1 special character   🔐', seconds: 2);
      return;
    }
    SharedPreferencesUtil().backupPassword = newPasswordController.text;
    hasPasswordSet = true;
    _snackBar('New password set   🎉');
    Navigator.of(context).pop();
    MixpanelManager().backupsPasswordSet();
  }

  _getTextField(
    TextEditingController controller, {
    String hintText = '',
    bool obscureText = true,
    VoidCallback? onVisibilityChanged,
  }) {
    return Container(
      width: double.maxFinite,
      padding: const EdgeInsets.fromLTRB(16, 4, 16, 4),
      margin: const EdgeInsets.fromLTRB(18, 0, 18, 0),
      decoration: const BoxDecoration(
        borderRadius: BorderRadius.all(Radius.circular(8)),
        border: GradientBoxBorder(
          gradient: LinearGradient(colors: [
            Color.fromARGB(127, 208, 208, 208),
            Color.fromARGB(127, 188, 99, 121),
            Color.fromARGB(127, 86, 101, 182),
            Color.fromARGB(127, 126, 190, 236)
          ]),
          width: 2,
        ),
        shape: BoxShape.rectangle,
      ),
      child: TextField(
        enabled: true,
        controller: controller,
        obscureText: obscureText,
        enableSuggestions: false,
        autocorrect: false,
        textInputAction: TextInputAction.done,
        decoration: InputDecoration(
            labelText: hintText,
            labelStyle: const TextStyle(fontSize: 14.0, color: Colors.grey),
            enabledBorder: InputBorder.none,
            focusedBorder: InputBorder.none,
            suffixIcon: IconButton(
              icon: Icon(
                obscureText ? Icons.visibility_off : Icons.visibility,
                color: Colors.grey.shade200,
              ),
              onPressed: onVisibilityChanged,
            )),
        // maxLines: 8,
        // minLines: 1,
        // keyboardType: TextInputType.multiline,
        style: TextStyle(fontSize: 14.0, color: Colors.grey.shade200),
      ),
    );
  }

  _snackBar(String content, {int seconds = 1}) {
    ScaffoldMessenger.of(context).showSnackBar(SnackBar(
      content: Text(content),
      duration: Duration(seconds: seconds),
    ));
  }
}
