import 'package:flutter/material.dart';
import 'package:url_launcher/url_launcher.dart';

class SupportPage extends StatelessWidget {
  const SupportPage({super.key});

  @override
  Widget build(BuildContext context) {
    return Scaffold(
      backgroundColor: Theme.of(context).colorScheme.primary,
      appBar: AppBar(
        title: const Text('Support'),
        backgroundColor: Theme.of(context).colorScheme.primary,
      ),
      body: Padding(
        padding: const EdgeInsets.all(4.0),
        child: ListView(
          children: [
            GestureDetector(
              onTap: () {
                launchUrl(Uri.parse('https://docs.basedhardware.com/assembly/Install_firmware/'));
              },
              child: const ListTile(
                title: Text('How to Update Bootloader'),
                trailing: Icon(Icons.arrow_forward_ios),
              ),
            ),
            GestureDetector(
              onTap: () {
                launchUrl(Uri.parse('https://docs.basedhardware.com/assembly/Install_firmware/'));
              },
              child: const ListTile(
                title: Text('How to Update Firmware Manually'),
                trailing: Icon(Icons.arrow_forward_ios),
              ),
            ),
          ],
        ),
      ),
    );
  }
}
