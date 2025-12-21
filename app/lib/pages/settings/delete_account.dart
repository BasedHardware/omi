import 'package:firebase_auth/firebase_auth.dart';
import 'package:flutter/material.dart';
import 'package:omi/backend/http/api/users.dart';
import 'package:omi/backend/preferences.dart';
import 'package:omi/core/app_shell.dart';
import 'package:omi/utils/analytics/mixpanel.dart';
import 'package:omi/utils/other/temp.dart';
import 'package:omi/utils/wal_file_manager.dart';
import 'package:omi/widgets/dialog.dart';
import 'package:gradient_borders/gradient_borders.dart';

class DeleteAccount extends StatefulWidget {
  const DeleteAccount({super.key});

  @override
  State<DeleteAccount> createState() => _DeleteAccountState();
}

class _DeleteAccountState extends State<DeleteAccount> {
  bool checkboxValue = false;
  bool isDeleteing = false;

  void updateCheckboxValue(bool value) {
    setState(() {
      checkboxValue = value;
    });
  }

  Future deleteAccountNow() async {
    setState(() {
      isDeleteing = true;
    });
    MixpanelManager().deleteAccountConfirmed();
    MixpanelManager().deleteUser();
    await deleteAccount();
    await FirebaseAuth.instance.signOut();
    await WalFileManager.clearAll();
    SharedPreferencesUtil().clear();
    setState(() {
      isDeleteing = false;
    });
    routeToPage(context, const AppShell(), replace: true);
  }

  @override
  Widget build(BuildContext context) {
    return PopScope(
      canPop: !isDeleteing,
      child: Scaffold(
        backgroundColor: Theme.of(context).colorScheme.primary,
        appBar: AppBar(
          backgroundColor: Theme.of(context).colorScheme.primary,
          title: const Text('Delete Account'),
        ),
        body: Padding(
          padding: const EdgeInsets.symmetric(horizontal: 10),
          child: Column(
            children: [
              const SizedBox(
                height: 10,
              ),
              const Padding(
                padding: EdgeInsets.symmetric(horizontal: 50),
                child: Text(
                  "Are you sure you want to delete your account?",
                  style: TextStyle(
                    fontSize: 24,
                  ),
                  textAlign: TextAlign.center,
                ),
              ),
              const SizedBox(
                height: 10,
              ),
              const Text(
                "This cannot be undone.",
                style: TextStyle(fontSize: 18),
              ),
              const SizedBox(
                height: 30,
              ),
              const ListTile(
                leading: Icon(Icons.message_rounded),
                title: Text("All of your memories and conversations will be permanently erased."),
              ),
              const ListTile(
                leading: Icon(Icons.person_pin_outlined),
                title: Text("Your Apps and Integrations will be disconnected effectively immediately."),
              ),
              const ListTile(
                leading: Icon(Icons.upload_file_outlined),
                title: Text(
                    "You can export your data before deleting your account, but once deleted, it cannot be recovered."),
              ),
              const Spacer(),
              Row(
                children: [
                  Checkbox(
                    value: checkboxValue,
                    onChanged: (value) {
                      if (value != null) {
                        updateCheckboxValue(value);
                      }
                    },
                  ),
                  SizedBox(
                    width: MediaQuery.of(context).size.width * 0.80,
                    child: const Text(
                        "I understand that deleting my account is permanent and all data, including memories and conversations, will be lost and cannot be recovered. "),
                  ),
                ],
              ),
              const SizedBox(
                height: 30,
              ),
              isDeleteing
                  ? const CircularProgressIndicator(
                      color: Colors.white,
                    )
                  : Container(
                      decoration: BoxDecoration(
                        border: const GradientBoxBorder(
                          gradient: LinearGradient(colors: [
                            Color.fromARGB(127, 208, 208, 208),
                            Color.fromARGB(127, 188, 99, 121),
                            Color.fromARGB(127, 86, 101, 182),
                            Color.fromARGB(127, 126, 190, 236)
                          ]),
                          width: 2,
                        ),
                        borderRadius: BorderRadius.circular(12),
                      ),
                      child: ElevatedButton(
                        onPressed: () {
                          if (checkboxValue) {
                            showDialog(
                                context: context,
                                builder: (c) {
                                  return getDialog(context, () {
                                    MixpanelManager().deleteAccountCancelled();
                                    Navigator.of(context).pop();
                                  }, () {
                                    deleteAccountNow();
                                    Navigator.of(context).pop();
                                  }, "Are you sure?\n",
                                      "This action is irreversible and will permanently delete your account and all associated data. Are you sure you want to proceed?",
                                      okButtonText: 'Delete Now', cancelButtonText: 'Go Back');
                                });
                          } else {
                            ScaffoldMessenger.of(context).showSnackBar(
                              const SnackBar(
                                content: Text(
                                    'Check the box to confirm you understand that deleting your account is permanent and irreversible.'),
                              ),
                            );
                          }
                        },
                        style: ElevatedButton.styleFrom(
                          backgroundColor: Colors.transparent,
                          shadowColor: const Color.fromARGB(255, 17, 17, 17),
                          shape: RoundedRectangleBorder(
                            borderRadius: BorderRadius.circular(12),
                          ),
                        ),
                        child: Container(
                          width: double.infinity,
                          height: 45,
                          alignment: Alignment.center,
                          child: const Text(
                            'Delete Account',
                            style: TextStyle(
                              fontWeight: FontWeight.w400,
                              fontSize: 18,
                              color: Color.fromARGB(255, 255, 255, 255),
                            ),
                          ),
                        ),
                      ),
                    ),
              const SizedBox(
                height: 70,
              ),
            ],
          ),
        ),
      ),
    );
  }
}
