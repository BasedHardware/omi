import 'package:flutter/material.dart';
import 'package:friend_private/backend/api_requests/cloud_storage.dart';
import 'package:friend_private/backend/mixpanel.dart';
import 'package:friend_private/backend/preferences.dart';
import 'package:friend_private/pages/backup/page.dart';
import 'package:url_launcher/url_launcher.dart';

class DeveloperSettingsPage extends StatefulWidget {
  const DeveloperSettingsPage({super.key});

  @override
  State<DeveloperSettingsPage> createState() => _DeveloperSettingsPageState();
}

class _DeveloperSettingsPageState extends State<DeveloperSettingsPage> {
  final TextEditingController gcpCredentialsController = TextEditingController();
  final TextEditingController gcpBucketNameController = TextEditingController();
  final TextEditingController deepgramAPIKeyController = TextEditingController();
  final TextEditingController openAIKeyController = TextEditingController();
  final TextEditingController webhookUrlController = TextEditingController();
  final TextEditingController transcriptServerUrlController = TextEditingController();

  bool savingSettingsLoading = false;

  @override
  void initState() {
    openAIKeyController.text = SharedPreferencesUtil().openAIApiKey;
    deepgramAPIKeyController.text = SharedPreferencesUtil().deepgramApiKey;
    gcpCredentialsController.text = SharedPreferencesUtil().gcpCredentials;
    gcpBucketNameController.text = SharedPreferencesUtil().gcpBucketName;
    webhookUrlController.text = SharedPreferencesUtil().webhookUrl;
    transcriptServerUrlController.text = SharedPreferencesUtil().transcriptServerUrl;
    super.initState();
  }

  @override
  Widget build(BuildContext context) {
    return GestureDetector(
      onTap: () => FocusScope.of(context).unfocus(),
      child: Scaffold(
        backgroundColor: Theme.of(context).colorScheme.primary,
        appBar: AppBar(
          backgroundColor: Theme.of(context).colorScheme.primary,
          title: const Text('Developer Settings'),
          actions: [
            MaterialButton(
              onPressed: savingSettingsLoading ? null : saveSettings,
              color: Colors.transparent,
              elevation: 0,
              child: const Padding(
                padding: EdgeInsets.symmetric(horizontal: 4.0),
                child: Text(
                  'Save',
                  style: TextStyle(color: Colors.deepPurple, fontWeight: FontWeight.w600, fontSize: 16),
                ),
              ),
            )
          ],
        ),
        body: Padding(
          padding: const EdgeInsets.symmetric(horizontal: 32),
          child: ListView(
            children: [
              const SizedBox(height: 32),
              _getText('Your own Developer Keys', bold: true),
              const SizedBox(height: 16.0),
              TextField(
                controller: openAIKeyController,
                obscureText: false,
                autocorrect: false,
                enabled: true,
                enableSuggestions: false,
                decoration: _getTextFieldDecoration('Open AI Key', hintText: 'sk-.......'),
                style: const TextStyle(color: Colors.white),
              ),
              TextField(
                controller: deepgramAPIKeyController,
                obscureText: false,
                autocorrect: false,
                enabled: true,
                enableSuggestions: false,
                decoration: _getTextFieldDecoration('Deepgram API Key', hintText: ''),
                style: const TextStyle(color: Colors.white),
              ),
              const SizedBox(height: 40),
              _getText('Store your audios in Google Cloud Storage', bold: true),
              const SizedBox(height: 16.0),
              TextField(
                controller: gcpCredentialsController,
                obscureText: false,
                autocorrect: false,
                enableSuggestions: false,
                enabled: true,
                decoration: _getTextFieldDecoration('GCP Credentials (Base64)'),
                style: const TextStyle(color: Colors.white),
              ),
              TextField(
                controller: gcpBucketNameController,
                obscureText: false,
                autocorrect: false,
                enabled: true,
                enableSuggestions: false,
                decoration: _getTextFieldDecoration('GCP Bucket Name'),
                style: const TextStyle(color: Colors.white),
              ),
              const SizedBox(height: 32),
              ListTile(
                contentPadding: const EdgeInsets.only(right: 8),
                title: const Text('JSON Import/Export memories'),
                trailing: const Icon(Icons.arrow_forward_ios, color: Colors.white, size: 16),
                onTap: () {
                  Navigator.of(context).push(MaterialPageRoute(builder: (context) => const BackupsPage()));
                },
              ),
              const SizedBox(height: 20),
              Container(
                width: double.infinity,
                height: 2,
                decoration: BoxDecoration(
                  color: Colors.white.withOpacity(0.2),
                  borderRadius: BorderRadius.circular(12),
                ),
              ),
              const SizedBox(height: 20),
              Row(
                crossAxisAlignment: CrossAxisAlignment.center,
                mainAxisAlignment: MainAxisAlignment.spaceBetween,
                children: [
                  const Text('Advanced Mode',
                      style: TextStyle(color: Colors.white, fontSize: 16, fontWeight: FontWeight.w600)),
                  GestureDetector(
                      onTap: () {
                        launchUrl(Uri.parse(
                            'https://github.com/BasedHardware/Friend/blob/main/apps/AppWithWearable/lib/pages/settings/advanced_mode.md'));
                        MixpanelManager().advancedModeDocsOpened();
                      },
                      child: const Padding(
                        padding: EdgeInsets.all(8.0),
                        child: Text(
                          'Docs',
                          style: TextStyle(
                            color: Colors.white,
                            fontSize: 14,
                            decoration: TextDecoration.underline,
                          ),
                        ),
                      ))
                ],
              ),
              const SizedBox(height: 16),
              _getText('Webhooks: Every time a new memory get\'s created, send the details to your own server.'),
              TextField(
                controller: webhookUrlController,
                obscureText: false,
                autocorrect: false,
                enabled: true,
                enableSuggestions: false,
                decoration: _getTextFieldDecoration('Webhook URL'),
                style: const TextStyle(color: Colors.white),
              ),
              // const SizedBox(height: 16),
              // _getText('Transcript Server URL: Send your audio files to your own server.'),
              // TextField(
              //   controller: transcriptServerUrlController,
              //   obscureText: false,
              //   autocorrect: false,
              //   enabled: true,
              //   enableSuggestions: false,
              //   decoration: _getTextFieldDecoration('Transcript Server URL'),
              //   style: const TextStyle(color: Colors.white),
              // ),
              const SizedBox(height: 64),
            ],
          ),
        ),
      ),
    );
  }

  _getTextFieldDecoration(String label, {IconButton? suffixIcon, bool canBeDisabled = false, String hintText = ''}) {
    return InputDecoration(
      labelText: label,
      enabled: true && canBeDisabled,
      hintText: hintText,
      // labelText: hintText,
      labelStyle: const TextStyle(
        fontSize: 16,
        color: Colors.grey,
        decoration: TextDecoration.underline,
      ),
      // bottom border
      enabledBorder: InputBorder.none,
      focusedBorder: const UnderlineInputBorder(
        borderSide: BorderSide(color: Colors.grey),
      ),
      suffixIcon: suffixIcon,
    );
  }

  _getText(String text, {bool canBeDisabled = false, bool underline = false, bool bold = false}) {
    return Text(
      text,
      style: TextStyle(
        color: true && canBeDisabled ? Colors.white.withOpacity(0.2) : Colors.white,
        decoration: underline ? TextDecoration.underline : TextDecoration.none,
        fontSize: 16,
        fontWeight: bold ? FontWeight.w600 : FontWeight.normal,
      ),
      // textAlign: TextAlign.center,
    );
  }

  void saveSettings() async {
    if (savingSettingsLoading) return;
    setState(() => savingSettingsLoading = true);
    final prefs = SharedPreferencesUtil();
    if (gcpCredentialsController.text.isNotEmpty && gcpBucketNameController.text.isNotEmpty) {
      try {
        await authenticateGCP(base64: gcpCredentialsController.text.trim());
      } catch (e) {
        ScaffoldMessenger.of(context).showSnackBar(const SnackBar(
          content: Text('Invalid GCP credentials or bucket name. Please check and try again.'),
        ));
        setState(() => savingSettingsLoading = false);
        return;
      }
    }

    // TODO: test openai + deepgram keys + bucket existence, before saving

    prefs.gcpCredentials = gcpCredentialsController.text.trim();
    prefs.gcpBucketName = gcpBucketNameController.text.trim();
    prefs.openAIApiKey = openAIKeyController.text.trim();
    prefs.deepgramApiKey = deepgramAPIKeyController.text.trim();
    prefs.webhookUrl = webhookUrlController.text.trim();
    prefs.transcriptServerUrl = transcriptServerUrlController.text.trim();

    MixpanelManager().settingsSaved();
    setState(() => savingSettingsLoading = false);
    ScaffoldMessenger.of(context).showSnackBar(const SnackBar(content: Text('Settings saved!')));
  }
}
