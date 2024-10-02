import 'package:flutter/material.dart';
import 'package:url_launcher/url_launcher.dart';
import 'package:friend_private/services/translation_service.dart';

import '../settings/widgets/expansion_tile_card.dart';

class SupportPage extends StatelessWidget {
  const SupportPage({super.key});

  @override
  Widget build(BuildContext context) {
    return Scaffold(
      backgroundColor: Theme.of(context).colorScheme.primary,
      appBar: AppBar(
        title:  Text(TranslationService.translate( 'Guides & Tutorials')),
        backgroundColor: Theme.of(context).colorScheme.primary,
      ),
      body: Padding(
        padding: const EdgeInsets.all(4.0),
        child: ListView(
          children: [
            ExpansionTileCard(
              title: TranslationService.translate( 'How to Update Firmware'),
              baseColor: Theme.of(context).colorScheme.primary,
              expandedColor: const Color.fromARGB(255, 29, 29, 29),
              elevation: 0,
              expandedTextStyle: TextStyle(color: Theme.of(context).textTheme.titleMedium!.color),
              collapsedTextStyle: TextStyle(color: Theme.of(context).textTheme.titleMedium!.color),
              children:  [
                Padding(
                  padding: EdgeInsets.only(top: 8.0, bottom: 16.0),
                  child: Column(
                    crossAxisAlignment: CrossAxisAlignment.start,
                    children: [
                      Text(
                  TranslationService.translate( 'To update the firmware, follow the steps below:'),
                        style: TextStyle(color: Color.fromARGB(255, 255, 255, 255)),
                      ),
                      SizedBox(height: 8),
                      Text(
                        TranslationService.translate( '1. Make sure your device is connected to the app.'),
                        style: TextStyle(color: Color.fromARGB(255, 255, 255, 255)),
                      ),
                      SizedBox(height: 8),
                      Text(
                        TranslationService.translate( '2. Go to the Device Settings page.'),
                        style: TextStyle(color: Color.fromARGB(255, 255, 255, 255)),
                      ),
                      SizedBox(height: 8),
                      Text(
                        TranslationService.translate( '3. Tap on the "Update Firmware" button.'),
                        style: TextStyle(color: Color.fromARGB(255, 255, 255, 255)),
                      ),
                      SizedBox(height: 8),
                      Text(
    TranslationService.translate( '4. Wait for the update to complete.'),
                        style: TextStyle(color: Color.fromARGB(255, 255, 255, 255)),
                      ),
                    ],
                  ),
                ),
              ],
            ),
            ExpansionTileCard(
              title: TranslationService.translate( 'My Device doesn\'t appear in the list after firmware update'),
              baseColor: Theme.of(context).colorScheme.primary,
              expandedColor: const Color.fromARGB(255, 29, 29, 29),
              elevation: 0,
              expandedTextStyle: TextStyle(color: Theme.of(context).textTheme.titleMedium!.color),
              collapsedTextStyle: TextStyle(color: Theme.of(context).textTheme.titleMedium!.color),
              children:  [
                Padding(
                  padding: EdgeInsets.all(16.0),
                  child: Column(
                    crossAxisAlignment: CrossAxisAlignment.start,
                    children: [
                      Text(
                  TranslationService.translate( 'If your device doesn\'t appear in the list after updating the firmware, try restarting it. If it keeps blinking after restarting and doesn\'t appear in list, then the update was not successful and got corrupted.\n'),
                        style: TextStyle(color: Color.fromARGB(255, 255, 255, 255)),
                      ),
                      Text(
                        TranslationService.translate( 'You can try updating the firmware manually by following the guide mentioned on this page.'),
                        style: TextStyle(color: Color.fromARGB(255, 255, 255, 255)),
                      ),
                    ],
                  ),
                ),
              ],
            ),
            ExpansionTileCard(
              title: TranslationService.translate( 'I am on v1.0.2 and can\'t update the firmware through the app'),
              baseColor: Theme.of(context).colorScheme.primary,
              expandedColor: const Color.fromARGB(255, 29, 29, 29),
              elevation: 0,
              expandedTextStyle: TextStyle(color: Theme.of(context).textTheme.titleMedium!.color),
              collapsedTextStyle: TextStyle(color: Theme.of(context).textTheme.titleMedium!.color),
              children:  [
                Padding(
                  padding: EdgeInsets.all(16.0),
                  child: Column(
                    crossAxisAlignment: CrossAxisAlignment.start,
                    children: [
                      Text(
                  TranslationService.translate( 'The app only supports updating the firmware from v1.0.3 onwards. If you are on v1.0.2 or below, you will need to update the firmware manually to v1.0.3 and bootloader to v0.9.0.\n'),
                        style: TextStyle(color: Color.fromARGB(255, 255, 255, 255)),
                      ),
                      Text(
                        TranslationService.translate( 'You can find the guide on how to update the firmware manually on this page.'),
                        style: TextStyle(color: Color.fromARGB(255, 255, 255, 255)),
                      ),
                    ],
                  ),
                ),
              ],
            ),
            ExpansionTileCard(
              title: TranslationService.translate( 'How to Update Bootloader'),
              baseColor: Theme.of(context).colorScheme.primary,
              expandedColor: const Color.fromARGB(255, 29, 29, 29),
              elevation: 0,
              expandedTextStyle: TextStyle(color: Theme.of(context).textTheme.titleMedium!.color),
              collapsedTextStyle: TextStyle(color: Theme.of(context).textTheme.titleMedium!.color),
              children: [
                InkWell(
                  onTap: () {
                    launchUrl(Uri.parse('https://github.com/BasedHardware/Omi/releases/tag/v1.0.3-firmware'));
                  },
                  child:  Padding(
                    padding: EdgeInsets.all(16.0),
                    child: Text(TranslationService.translate( "Click here to view the guide"),
                        style: TextStyle(color: Color.fromARGB(255, 255, 255, 255))),
                  ),
                )
              ],
            ),
            ExpansionTileCard(
              title: TranslationService.translate( 'How to Update Firmware Manually'),
              baseColor: Theme.of(context).colorScheme.primary,
              expandedColor: const Color.fromARGB(255, 29, 29, 29),
              elevation: 0,
              expandedTextStyle: TextStyle(color: Theme.of(context).textTheme.titleMedium!.color),
              collapsedTextStyle: TextStyle(color: Theme.of(context).textTheme.titleMedium!.color),
              children: [
                InkWell(
                  onTap: () {
                    launchUrl(Uri.parse('https://github.com/BasedHardware/Omi/releases/tag/v1.0.3-firmware'));
                  },
                  child:  Padding(
                    padding: EdgeInsets.all(16.0),
                    child: Text(TranslationService.translate( "Click here to view the guide"),
                        style: TextStyle(color: Color.fromARGB(255, 255, 255, 255))),
                  ),
                )
              ],
            ),
          ],
        ),
      ),
    );
  }
}
