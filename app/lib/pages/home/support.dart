import 'package:flutter/material.dart';
import 'package:friend_private/widgets/dialog.dart';
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
                showDialog(
                  context: context,
                  builder: (c) => getDialog(
                    context,
                    () => Navigator.pop(context),
                    () {},
                    singleButton: true,
                    'Device Not Appearing After Update',
                    'If your device doesn\'t appear in the list after updating the firmware, try restarting it. If it keeps blinking after restarting and doesn\'t appear in list, then the update was not successful and got corrupted.\n\nYou can try updating the firmware manually by following the guide mentioned on this page.',
                    okButtonText: 'Ok, I understand',
                  ),
                );
              },
              child: const ListTile(
                title: Text('My Device doesn\'t appear in the list or it keeps blinking after updating the firmware'),
                trailing: Icon(Icons.arrow_forward_ios),
              ),
            ),
            GestureDetector(
              onTap: () {
                showDialog(
                  context: context,
                  builder: (c) => getDialog(
                    context,
                    () => Navigator.pop(context),
                    () {},
                    singleButton: true,
                    'Firmware Update on v1.0.2',
                    'The app only supports updating the firmware from v1.0.3 onwards. If you are on v1.0.2 or below, you will need to update the firmware manually to v1.0.3 and bootloader to v0.9.0.\n\nYou can find the guide on how to update the firmware manually on this page.',
                    okButtonText: 'Ok, I understand',
                  ),
                );
              },
              child: const ListTile(
                title: Text('I am on v1.0.2 and can\'t update the firmware through the app'),
                trailing: Icon(Icons.arrow_forward_ios),
              ),
            ),
            GestureDetector(
              onTap: () {
                launchUrl(Uri.parse('https://github.com/BasedHardware/Omi/releases/tag/v1.0.3-firmware'));
              },
              child: const ListTile(
                title: Text('How to Update Bootloader'),
                trailing: Icon(Icons.arrow_forward_ios),
              ),
            ),
            GestureDetector(
              onTap: () {
                launchUrl(Uri.parse('https://github.com/BasedHardware/Omi/releases/tag/v1.0.3-firmware'));
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
