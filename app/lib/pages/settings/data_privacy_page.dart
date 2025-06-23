import 'package:flutter/gestures.dart';
import 'package:flutter/material.dart';
import 'package:omi/backend/schema/app.dart';
import 'package:omi/pages/apps/app_detail/app_detail.dart';
import 'package:omi/pages/settings/widgets/data_protection_section.dart';
import 'package:omi/providers/app_provider.dart';
import 'package:omi/providers/user_provider.dart';
import 'package:omi/utils/other/temp.dart';
import 'package:provider/provider.dart';
import 'package:url_launcher/url_launcher.dart';

class DataPrivacyPage extends StatefulWidget {
  const DataPrivacyPage({super.key});

  @override
  State<DataPrivacyPage> createState() => _DataPrivacyPageState();
}

class _DataPrivacyPageState extends State<DataPrivacyPage> {
  @override
  void initState() {
    super.initState();
  }

  Widget _buildIntroSection(BuildContext context) {
    return Container(
      padding: const EdgeInsets.symmetric(horizontal: 16, vertical: 24),
      decoration: BoxDecoration(
        color: const Color(0xFF1A1A1A),
        borderRadius: BorderRadius.circular(16),
      ),
      child: Column(
        children: [
          const Text(
            '🛡️',
            style: TextStyle(fontSize: 64),
          ),
          const SizedBox(height: 16),
          const Text(
            'Your Privacy, Your Control',
            style: TextStyle(fontSize: 24, fontWeight: FontWeight.bold, color: Colors.white),
            textAlign: TextAlign.center,
          ),
          const SizedBox(height: 12),
          Padding(
            padding: const EdgeInsets.symmetric(horizontal: 16.0),
            child: RichText(
              textAlign: TextAlign.center,
              text: TextSpan(
                style: TextStyle(fontSize: 16, color: Colors.grey.shade400, height: 1.5),
                children: [
                  const TextSpan(
                    text:
                        'At Omi, we are committed to protecting your privacy. This page allows you to control how your data is stored and used. ',
                  ),
                  TextSpan(
                    text: 'Learn more...',
                    style: TextStyle(
                      color: Colors.deepPurple.shade300,
                      decoration: TextDecoration.underline,
                      decorationColor: Colors.deepPurple.shade300,
                    ),
                    recognizer: TapGestureRecognizer()
                      ..onTap = () async {
                        final url = Uri.parse('https://www.omi.me/pages/privacy');
                        if (await canLaunchUrl(url)) {
                          await launchUrl(url, mode: LaunchMode.externalApplication);
                        }
                      },
                  ),
                ],
              ),
            ),
          ),
        ],
      ),
    );
  }

  String _getAccessDescription(App app) {
    List<String> accessTypes = [];
    if (app.hasConversationsAccess()) {
      accessTypes.add('Conversations');
    }
    if (app.hasMemoriesAccess()) {
      accessTypes.add('Memories');
    }

    String accessDescription = '';
    if (accessTypes.isNotEmpty) {
      accessDescription = 'Accesses ${accessTypes.join(' & ')}';
    }

    final trigger = app.externalIntegration?.getTriggerOnString();
    String triggerDescription = '';
    if (trigger != null && trigger != 'Unknown') {
      triggerDescription = 'triggered by ${trigger.toLowerCase()}';
    }

    if (accessDescription.isNotEmpty && triggerDescription.isNotEmpty) {
      return '$accessDescription and is $triggerDescription.';
    }
    if (accessDescription.isNotEmpty) {
      return '$accessDescription.';
    }
    if (triggerDescription.isNotEmpty) {
      var sentence = 'Is $triggerDescription.';
      return sentence[0].toUpperCase() + sentence.substring(1);
    }

    return 'No specific data access configured.';
  }

  @override
  Widget build(BuildContext context) {
    return Consumer<UserProvider>(
      builder: (context, provider, child) {
        final isLoading = provider.isLoading;
        final isMigrating = provider.isMigrating;

        return Scaffold(
          backgroundColor: Theme.of(context).colorScheme.primary,
          appBar: AppBar(
            backgroundColor: Theme.of(context).colorScheme.primary,
            automaticallyImplyLeading: true,
            title: const Text(
              'Data & Privacy',
              style: TextStyle(fontSize: 22, fontWeight: FontWeight.w600),
            ),
            centerTitle: true,
            leading: IconButton(
              icon: const Icon(Icons.arrow_back_ios_new),
              onPressed: () => Navigator.pop(context),
            ),
            elevation: 0,
          ),
          body: Stack(
            children: [
              ListView(
                padding: const EdgeInsets.all(16.0),
                children: [
                  _buildIntroSection(context),
                  const SizedBox(height: 32),
                  const Text(
                    'Data Protection Level',
                    style: TextStyle(color: Colors.white, fontSize: 18, fontWeight: FontWeight.bold),
                  ),
                  const SizedBox(height: 8),
                  Text(
                    'Choose how your data is stored and protected on our servers.',
                    style: TextStyle(color: Colors.grey.shade400, fontSize: 14),
                  ),
                  const SizedBox(height: 16),
                  const DataProtectionSection(),
                  const SizedBox(height: 24),
                  const Divider(color: Colors.grey),
                  const SizedBox(height: 24),
                  Consumer<AppProvider>(
                    builder: (context, appProvider, child) {
                      final appsWithDataAccess =
                          appProvider.apps.where((app) => app.enabled && app.worksExternally()).toList();

                      return Column(
                        crossAxisAlignment: CrossAxisAlignment.start,
                        children: [
                          const Text(
                            'App Access',
                            style: TextStyle(color: Colors.white, fontSize: 18, fontWeight: FontWeight.bold),
                          ),
                          const SizedBox(height: 8),
                          Text(
                            'The following apps can access your data. Tap on an app to manage its permissions.',
                            style: TextStyle(color: Colors.grey.shade400, fontSize: 14),
                          ),
                          const SizedBox(height: 16),
                          if (appsWithDataAccess.isEmpty)
                            Container(
                              width: double.infinity,
                              padding: const EdgeInsets.symmetric(vertical: 32.0, horizontal: 16.0),
                              decoration: BoxDecoration(
                                color: const Color(0xFF1A1A1A),
                                borderRadius: BorderRadius.circular(12),
                              ),
                              child: Center(
                                child: Column(
                                  children: [
                                    Icon(Icons.apps_outlined, color: Colors.grey.shade600, size: 32),
                                    const SizedBox(height: 16),
                                    Text(
                                      'No installed apps have external access to your data.',
                                      textAlign: TextAlign.center,
                                      style: TextStyle(color: Colors.grey.shade400),
                                    ),
                                  ],
                                ),
                              ),
                            )
                          else
                            Column(
                              children: appsWithDataAccess.map((app) {
                                return Card(
                                  color: const Color(0xFF1A1A1A),
                                  margin: const EdgeInsets.only(bottom: 10),
                                  shape: RoundedRectangleBorder(
                                    borderRadius: BorderRadius.circular(12),
                                    side: BorderSide(color: Colors.grey.shade800, width: 1),
                                  ),
                                  elevation: 0,
                                  clipBehavior: Clip.antiAlias,
                                  child: ListTile(
                                    contentPadding: const EdgeInsets.symmetric(horizontal: 16, vertical: 8),
                                    leading: CircleAvatar(
                                      backgroundImage: NetworkImage(app.getImageUrl()),
                                    ),
                                    title: Text(app.getName()),
                                    subtitle: Text(
                                      _getAccessDescription(app),
                                      style: TextStyle(color: Colors.grey.shade400, fontSize: 12),
                                    ),
                                    trailing: const Icon(Icons.arrow_forward_ios, size: 16),
                                    onTap: () {
                                      routeToPage(context, AppDetailPage(app: app, preventAutoOpenHomePage: true));
                                    },
                                  ),
                                );
                              }).toList(),
                            ),
                        ],
                      );
                    },
                  ),
                  const SizedBox(height: 32),
                ],
              ),
              if (isLoading && !isMigrating)
                Container(
                  color: Colors.black.withOpacity(0.5),
                  child: const Center(
                    child: CircularProgressIndicator(),
                  ),
                ),
            ],
          ),
        );
      },
    );
  }
}
