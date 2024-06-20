import 'package:flutter/material.dart';
import 'package:friend_private/pages/home/page.dart';
import 'package:friend_private/pages/onboarding/import/import.dart';
import 'package:friend_private/widgets/device_widget.dart';

class HasBackupPage extends StatefulWidget {
  const HasBackupPage({super.key});

  @override
  State<HasBackupPage> createState() => _HasBackupPageState();
}

class _HasBackupPageState extends State<HasBackupPage> {
  @override
  Widget build(BuildContext context) {
    return PopScope(
      canPop: false,
      child: Scaffold(
        backgroundColor: Theme.of(context).colorScheme.primary,
        appBar: AppBar(backgroundColor: Theme.of(context).colorScheme.primary),
        body: Padding(
          padding: const EdgeInsets.fromLTRB(16, 0, 16, 80),
          child: Column(
            mainAxisAlignment: MainAxisAlignment.spaceBetween,
            children: [
              const DeviceAnimationWidget(),
              const SizedBox(height: 48),
              const Padding(
                padding: EdgeInsets.all(24),
                child: Column(
                  children: [
                    Text(
                      'Already had an account? Press "Import" to continue, otherwise press "Skip".',
                      style: TextStyle(color: Colors.white, fontSize: 15, height: 1.5),
                      textAlign: TextAlign.center,
                    ),
                  ],
                ),
              ),
              Row(
                mainAxisAlignment: MainAxisAlignment.center,
                children: [
                  MaterialButton(
                    onPressed: () {
                      Navigator.of(context).pushReplacement(MaterialPageRoute(builder: (c) => const HomePageWrapper()));
                    },
                    child: const Text('Skip', style: TextStyle(decoration: TextDecoration.underline)),
                  ),
                  MaterialButton(
                    onPressed: () {
                      Navigator.of(context).push(MaterialPageRoute(builder: (c) => const ImportBackupPage()));
                    },
                    shape: RoundedRectangleBorder(
                      borderRadius: BorderRadius.circular(8),
                      side: const BorderSide(color: Colors.deepPurple),
                    ),
                    color: Colors.deepPurple,
                    child: const Text(
                      'Import',
                      style: TextStyle(color: Colors.white),
                    ),
                  ),
                ],
              ),
            ],
            // TODO: include an option for setting up backup
          ),
        ),
      ),
    );
  }
}
