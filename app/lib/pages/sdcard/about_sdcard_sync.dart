import 'package:flutter/material.dart';

class AboutSdCardSync extends StatefulWidget {
  const AboutSdCardSync({super.key});

  @override
  State<AboutSdCardSync> createState() => _AboutSdCardSyncState();
}

class _AboutSdCardSyncState extends State<AboutSdCardSync> {
  @override
  Widget build(BuildContext context) {
    return Scaffold(
      backgroundColor: Theme.of(context).colorScheme.primary,
      appBar: AppBar(
        backgroundColor: Theme.of(context).colorScheme.primary,
        automaticallyImplyLeading: true,
        centerTitle: true,
        leading: IconButton(
          icon: const Icon(Icons.arrow_back_ios_new),
          onPressed: () {
            Navigator.pop(context);
          },
        ),
        elevation: 0,
      ),
      body: Center(
        child: Column(
          mainAxisAlignment: MainAxisAlignment.start,
          children: [
            Container(
              decoration: BoxDecoration(
                color: const Color(0xFF1F1F25),
                borderRadius: BorderRadius.circular(24),
              ),
              padding: const EdgeInsets.symmetric(horizontal: 24, vertical: 24),
              margin: const EdgeInsets.all(24),
              child: const Column(
                crossAxisAlignment: CrossAxisAlignment.center,
                mainAxisAlignment: MainAxisAlignment.center,
                mainAxisSize: MainAxisSize.min,
                children: [
                  Center(
                    child: Text(
                      'How does it work?',
                      style: TextStyle(
                        color: Colors.white,
                        fontSize: 28,
                        fontWeight: FontWeight.w500,
                      ),
                    ),
                  ),
                  SizedBox(height: 16),
                  Text(
                    'SD Card Sync will import your memories from the SD Card to the app',
                    style: TextStyle(color: Colors.grey, fontSize: 16),
                    textAlign: TextAlign.center,
                  ),
                  SizedBox(height: 24),
                  Icon(Icons.sd_card, size: 40, color: Colors.grey),
                  SizedBox(height: 8),
                  Text(
                    'Checks for audio files on the SD Card',
                    textAlign: TextAlign.center,
                    style: TextStyle(color: Colors.white, fontSize: 16),
                  ),
                  SizedBox(height: 18),
                  Icon(Icons.upload_rounded, size: 40, color: Colors.grey),
                  SizedBox(height: 8),
                  Text(
                    'Omi then syncs the audio files with the server',
                    textAlign: TextAlign.center,
                    style: TextStyle(color: Colors.white, fontSize: 16),
                  ),
                  SizedBox(height: 18),
                  Icon(Icons.wifi_protected_setup_sharp, size: 40, color: Colors.grey),
                  SizedBox(height: 8),
                  Text(
                    'The server processes the audio files and creates memories',
                    textAlign: TextAlign.center,
                    style: TextStyle(color: Colors.white, fontSize: 16),
                  ),
                ],
              ),
            ),
          ],
        ),
      ),
    );
  }
}
