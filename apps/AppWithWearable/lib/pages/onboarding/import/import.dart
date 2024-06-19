import 'package:flutter/material.dart';
import 'package:friend_private/utils/backups.dart';
import 'package:friend_private/widgets/device_widget.dart';
import 'package:gradient_borders/box_borders/gradient_box_border.dart';

class ImportBackupPage extends StatefulWidget {
  const ImportBackupPage({super.key});

  @override
  State<ImportBackupPage> createState() => _ImportBackupPageState();
}

class _ImportBackupPageState extends State<ImportBackupPage> {
  TextEditingController uidController = TextEditingController();
  TextEditingController passwordController = TextEditingController();

  bool passwordVisible = true;

  @override
  Widget build(BuildContext context) {
    return PopScope(
      canPop: true,
      child: GestureDetector(
        onTap: () => FocusScope.of(context).unfocus(),
        child: Scaffold(
          backgroundColor: Theme.of(context).colorScheme.primary,
          appBar: AppBar(
              backgroundColor: Theme.of(context).colorScheme.primary,
              leading: IconButton(
                icon: const Icon(Icons.arrow_back_ios_new),
                onPressed: () => Navigator.pop(context),
              )),
          body: Padding(
            padding: const EdgeInsets.symmetric(horizontal: 16),
            child: ListView(
              children: [
                const DeviceAnimationWidget(),
                const SizedBox(height: 48),
                _getTextField(uidController, hintText: 'Previous User ID', hasSuffixIcon: false, obscureText: false),
                const SizedBox(height: 12),
                _getTextField(passwordController, hintText: 'Backups Password', obscureText: passwordVisible,
                    onVisibilityChanged: () {
                  setState(() {
                    passwordVisible = !passwordVisible;
                  });
                }),
                const SizedBox(height: 40),
                Center(
                  child: MaterialButton(
                    onPressed: () {
                      // Navigator.of(context)
                      //     .pushReplacement(MaterialPageRoute(builder: (c) => const HomePageWrapper()));
                    },
                    shape: RoundedRectangleBorder(
                      borderRadius: BorderRadius.circular(8),
                      side: const BorderSide(color: Colors.deepPurple),
                    ),
                    padding: const EdgeInsets.symmetric(horizontal: 32, vertical: 16),
                    color: Colors.deepPurple,
                    child: const Text(
                      'Import',
                      style: TextStyle(color: Colors.white),
                    ),
                  ),
                ),
              ],
            ),
          ),
        ),
      ),
    );
  }

  _import() async {
    if (uidController.text.isEmpty || passwordController.text.isEmpty) return;
    if (uidController.text.length < 36) {
      _snackBar('Invalid User ID');
      return;
    }
    if (passwordController.text.length < 8) {
      _snackBar('Invalid Password');
      return;
    }
    var memoriesImported = await retrieveBackup(uidController.text, passwordController.text);
    debugPrint('Memories Imported: $memoriesImported');
  }

  _snackBar(String content, {int seconds = 1}) {
    ScaffoldMessenger.of(context).showSnackBar(SnackBar(
      content: Text(content),
      duration: Duration(seconds: seconds),
    ));
  }

  _getTextField(
    TextEditingController controller, {
    String hintText = '',
    bool obscureText = true,
    bool hasSuffixIcon = true,
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
            suffixIcon: hasSuffixIcon
                ? IconButton(
                    icon: Icon(
                      obscureText ? Icons.visibility_off : Icons.visibility,
                      color: Colors.grey.shade200,
                    ),
                    onPressed: onVisibilityChanged,
                  )
                : null),
        // maxLines: 8,
        // minLines: 1,
        // keyboardType: TextInputType.multiline,
        style: TextStyle(fontSize: 14.0, color: Colors.grey.shade200),
      ),
    );
  }
}
