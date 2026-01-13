import 'package:flutter/material.dart';

import 'package:firebase_auth/firebase_auth.dart';
import 'package:gradient_borders/gradient_borders.dart';

import 'package:omi/backend/http/api/users.dart';
import 'package:omi/backend/preferences.dart';
import 'package:omi/core/app_shell.dart';
import 'package:omi/utils/analytics/mixpanel.dart';
import 'package:omi/utils/l10n_extensions.dart';
import 'package:omi/utils/other/temp.dart';
import 'package:omi/utils/wal_file_manager.dart';
import 'package:omi/widgets/dialog.dart';

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
          title: Text(context.l10n.deleteAccountTitle),
        ),
        body: Padding(
          padding: const EdgeInsets.symmetric(horizontal: 10),
          child: Column(
            children: [
              const SizedBox(
                height: 10,
              ),
              Padding(
                padding: const EdgeInsets.symmetric(horizontal: 50),
                child: Text(
                  context.l10n.deleteAccountConfirm,
                  style: const TextStyle(
                    fontSize: 24,
                  ),
                  textAlign: TextAlign.center,
                ),
              ),
              const SizedBox(
                height: 10,
              ),
              Text(
                context.l10n.cannotBeUndone,
                style: const TextStyle(fontSize: 18),
              ),
              const SizedBox(
                height: 30,
              ),
              ListTile(
                leading: const Icon(Icons.message_rounded),
                title: Text(context.l10n.allDataErased),
              ),
              ListTile(
                leading: const Icon(Icons.person_pin_outlined),
                title: Text(context.l10n.appsDisconnected),
              ),
              ListTile(
                leading: const Icon(Icons.upload_file_outlined),
                title: Text(context.l10n.exportBeforeDelete),
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
                    child: Text(context.l10n.deleteAccountCheckbox),
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
                                  }, context.l10n.areYouSure, context.l10n.deleteAccountFinal,
                                      okButtonText: context.l10n.deleteNow, cancelButtonText: context.l10n.goBack);
                                });
                          } else {
                            ScaffoldMessenger.of(context).showSnackBar(
                              SnackBar(
                                content: Text(context.l10n.checkBoxToConfirm),
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
