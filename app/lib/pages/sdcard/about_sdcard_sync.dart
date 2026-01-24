import 'package:flutter/material.dart';

import 'package:omi/utils/l10n_extensions.dart';

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
              child: Column(
                crossAxisAlignment: CrossAxisAlignment.center,
                mainAxisAlignment: MainAxisAlignment.center,
                mainAxisSize: MainAxisSize.min,
                children: [
                  Center(
                    child: Text(
                      context.l10n.howDoesItWork,
                      style: const TextStyle(
                        color: Colors.white,
                        fontSize: 28,
                        fontWeight: FontWeight.w500,
                      ),
                    ),
                  ),
                  const SizedBox(height: 16),
                  Text(
                    context.l10n.sdCardSyncDescription,
                    style: const TextStyle(color: Colors.grey, fontSize: 16),
                    textAlign: TextAlign.center,
                  ),
                  const SizedBox(height: 24),
                  const Icon(Icons.sd_card, size: 40, color: Colors.grey),
                  const SizedBox(height: 8),
                  Text(
                    context.l10n.checksForAudioFiles,
                    textAlign: TextAlign.center,
                    style: const TextStyle(color: Colors.white, fontSize: 16),
                  ),
                  const SizedBox(height: 18),
                  const Icon(Icons.upload_rounded, size: 40, color: Colors.grey),
                  const SizedBox(height: 8),
                  Text(
                    context.l10n.omiSyncsAudioFiles,
                    textAlign: TextAlign.center,
                    style: const TextStyle(color: Colors.white, fontSize: 16),
                  ),
                  const SizedBox(height: 18),
                  const Icon(Icons.wifi_protected_setup_sharp, size: 40, color: Colors.grey),
                  const SizedBox(height: 8),
                  Text(
                    context.l10n.serverProcessesAudio,
                    textAlign: TextAlign.center,
                    style: const TextStyle(color: Colors.white, fontSize: 16),
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
