import 'package:flutter/material.dart';
import 'package:friend_private/backend/api_requests/cloud_storage.dart';
import 'package:friend_private/backend/mixpanel.dart';
import 'package:friend_private/backend/preferences.dart';
import 'package:friend_private/backend/utils.dart';
import 'package:friend_private/pages/plugins/page.dart';
import 'package:friend_private/pages/speaker_id/page.dart';
import 'package:url_launcher/url_launcher.dart';

class SettingsPage extends StatefulWidget {
  const SettingsPage({super.key});

  @override
  State<SettingsPage> createState() => _SettingsPageState();
}

class _SettingsPageState extends State<SettingsPage> {
  final TextEditingController openaiApiKeyController = TextEditingController();
  final TextEditingController gcpCredentialsController = TextEditingController();
  final TextEditingController gcpBucketNameController = TextEditingController();
  bool openaiApiIsVisible = false;
  late String _selectedLanguage;
  late bool useFriendAPIKeys;
  late bool optInAnalytics;
  late bool devModeEnabled;
  late bool coachIsChecked;
  late bool reconnectNotificationIsChecked;

  @override
  void initState() {
    openaiApiKeyController.text = SharedPreferencesUtil().openAIApiKey;
    gcpCredentialsController.text = SharedPreferencesUtil().gcpCredentials;
    gcpBucketNameController.text = SharedPreferencesUtil().gcpBucketName;

    _selectedLanguage = SharedPreferencesUtil().recordingsLanguage;
    useFriendAPIKeys = SharedPreferencesUtil().useFriendApiKeys;
    optInAnalytics = SharedPreferencesUtil().optInAnalytics;
    devModeEnabled = SharedPreferencesUtil().devModeEnabled;
    coachIsChecked = SharedPreferencesUtil().coachIsChecked;
    reconnectNotificationIsChecked = SharedPreferencesUtil().reconnectNotificationIsChecked;
    super.initState();
  }

  @override
  Widget build(BuildContext context) {
    return Scaffold(
      backgroundColor: Theme.of(context).colorScheme.primary,
      appBar: AppBar(
        backgroundColor: Theme.of(context).colorScheme.surface,
        automaticallyImplyLeading: true,
        title: const Text('Settings'),
        centerTitle: false,
        elevation: 0,
        actions: [
          MaterialButton(
            onPressed: _saveSettings,
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
        padding: EdgeInsets.only(bottom: MediaQuery.of(context).viewInsets.bottom, left: 8, right: 8),
        child: SingleChildScrollView(
          physics: const AlwaysScrollableScrollPhysics(),
          padding: const EdgeInsets.symmetric(horizontal: 16.0),
          child: Column(
            children: [
              const SizedBox(height: 32.0),
              const Padding(
                padding: EdgeInsets.symmetric(horizontal: 0),
                child: Align(
                  alignment: Alignment.centerLeft,
                  child: Text(
                    'RECORDING SETTINGS',
                    style: TextStyle(color: Colors.white, fontSize: 14, fontWeight: FontWeight.w600),
                  ),
                ),
              ),
              const SizedBox(height: 12),
              Center(
                  child: Container(
                height: 38,
                decoration: BoxDecoration(
                  border: Border.all(color: Colors.white),
                  borderRadius: BorderRadius.circular(14),
                ),
                padding: const EdgeInsets.symmetric(vertical: 8, horizontal: 12),
                child: DropdownButton<String>(
                  menuMaxHeight: 350,
                  value: _selectedLanguage,
                  onChanged: (String? newValue) {
                    setState(() {
                      _selectedLanguage = newValue!;
                    });
                  },
                  dropdownColor: Colors.black,
                  style: const TextStyle(color: Colors.white, fontSize: 16),
                  underline: Container(
                    height: 0,
                    color: Colors.white,
                  ),
                  isExpanded: true,
                  itemHeight: 48,
                  items: availableLanguages.keys.map<DropdownMenuItem<String>>((String key) {
                    return DropdownMenuItem<String>(
                      value: availableLanguages[key],
                      child: Text(
                        '$key (${availableLanguages[key]})',
                        style: const TextStyle(color: Colors.white, fontWeight: FontWeight.w500, fontSize: 16),
                      ),
                    );
                  }).toList(),
                ),
              )),
              const SizedBox(height: 24.0),
              const Align(
                alignment: Alignment.centerLeft,
                child: Text(
                  'NOTIFICATIONS',
                  style: TextStyle(
                    color: Colors.white,
                  ),
                  textAlign: TextAlign.start,
                ),
              ),
              InkWell(
                onTap: () {
                  setState(() {
                    if (coachIsChecked) {
                      coachIsChecked = false;
                      SharedPreferencesUtil().coachIsChecked = false;
                    } else {
                      coachIsChecked = true;
                      SharedPreferencesUtil().coachIsChecked = true;
                    }
                  });
                },
                child: Padding(
                  padding: const EdgeInsets.fromLTRB(0, 8.0, 8.0, 0),
                  child: Row(
                    mainAxisAlignment: MainAxisAlignment.spaceBetween,
                    children: [
                      const Text(
                        'Conversation coach',
                        style: TextStyle(
                          color: Color.fromARGB(255, 150, 150, 150),
                        ),
                      ),
                      Container(
                        decoration: BoxDecoration(
                          color: coachIsChecked
                              ? const Color.fromARGB(255, 150, 150, 150)
                              : Colors.transparent, // Fill color when checked
                          border: Border.all(
                            color: const Color.fromARGB(255, 150, 150, 150),
                            width: 2,
                          ),
                          borderRadius: BorderRadius.circular(12),
                        ),
                        width: 22,
                        height: 22,
                        child: coachIsChecked // Show the icon only when checked
                            ? const Icon(
                                Icons.check,
                                color: Colors.white, // Tick color
                                size: 18,
                              )
                            : null, // No icon when unchecked
                      ),
                    ],
                  ),
                ),
              ),
              InkWell(
                onTap: () {
                  setState(() {
                    if (reconnectNotificationIsChecked) {
                      reconnectNotificationIsChecked = false;
                      SharedPreferencesUtil().reconnectNotificationIsChecked = false;
                    } else {
                      reconnectNotificationIsChecked = true;
                      SharedPreferencesUtil().reconnectNotificationIsChecked = true;
                    }
                  });
                },
                child: Padding(
                  padding: const EdgeInsets.fromLTRB(0, 12, 8.0, 0),
                  child: Row(
                    mainAxisAlignment: MainAxisAlignment.spaceBetween,
                    children: [
                      const Text(
                        'Reminder to reconnect',
                        style: TextStyle(
                          color: Color.fromARGB(255, 150, 150, 150),
                        ),
                      ),
                      Container(
                        decoration: BoxDecoration(
                          color: reconnectNotificationIsChecked
                              ? const Color.fromARGB(255, 150, 150, 150)
                              : Colors.transparent, // Fill color when checked
                          border: Border.all(
                            color: const Color.fromARGB(255, 150, 150, 150),
                            width: 2,
                          ),
                          borderRadius: BorderRadius.circular(12),
                        ),
                        width: 22,
                        height: 22,
                        child: reconnectNotificationIsChecked // Show the icon only when checked
                            ? const Icon(
                                Icons.check,
                                color: Colors.white, // Tick color
                                size: 18,
                              )
                            : null, // No icon when unchecked
                      ),
                    ],
                  ),
                ),
              ),
              const SizedBox(height: 24.0),
              const Align(
                alignment: Alignment.centerLeft,
                child: Text(
                  'PREFERENCES',
                  style: TextStyle(
                    color: Colors.white,
                  ),
                  textAlign: TextAlign.start,
                ),
              ),
              InkWell(
                onTap: () {
                  setState(() {
                    if (optInAnalytics) {
                      optInAnalytics = false;
                      SharedPreferencesUtil().optInAnalytics = false;
                    } else {
                      optInAnalytics = true;
                      SharedPreferencesUtil().optInAnalytics = true;
                    }
                  });
                },
                child: Padding(
                  padding: const EdgeInsets.fromLTRB(0, 12, 8.0, 0),
                  child: Row(
                    mainAxisAlignment: MainAxisAlignment.spaceBetween,
                    children: [
                      const Text(
                        'Opt In Analytics',
                        style: TextStyle(
                          color: Color.fromARGB(255, 150, 150, 150),
                        ),
                      ),
                      Container(
                        decoration: BoxDecoration(
                          color: optInAnalytics
                              ? const Color.fromARGB(255, 150, 150, 150)
                              : Colors.transparent, // Fill color when checked
                          border: Border.all(
                            color: const Color.fromARGB(255, 150, 150, 150),
                            width: 2,
                          ),
                          borderRadius: BorderRadius.circular(12),
                        ),
                        width: 22,
                        height: 22,
                        child: optInAnalytics // Show the icon only when checked
                            ? const Icon(
                                Icons.check,
                                color: Colors.white, // Tick color
                                size: 18,
                              )
                            : null, // No icon when unchecked
                      ),
                    ],
                  ),
                ),
              ),
              InkWell(
                onTap: () {
                  setState(() {
                    if (devModeEnabled) {
                      devModeEnabled = false;
                      SharedPreferencesUtil().devModeEnabled = false;
                    } else {
                      devModeEnabled = true;
                      SharedPreferencesUtil().devModeEnabled = true;
                    }
                  });
                },
                child: Padding(
                  padding: const EdgeInsets.fromLTRB(0, 12, 8.0, 0),
                  child: Row(
                    mainAxisAlignment: MainAxisAlignment.spaceBetween,
                    children: [
                      const Text(
                        'Developer Mode',
                        style: TextStyle(
                          color: Color.fromARGB(255, 150, 150, 150),
                        ),
                      ),
                      Container(
                        decoration: BoxDecoration(
                          color: devModeEnabled
                              ? const Color.fromARGB(255, 150, 150, 150)
                              : Colors.transparent, // Fill color when checked
                          border: Border.all(
                            color: const Color.fromARGB(255, 150, 150, 150),
                            width: 2,
                          ),
                          borderRadius: BorderRadius.circular(12),
                        ),
                        width: 22,
                        height: 22,
                        child: devModeEnabled // Show the icon only when checked
                            ? const Icon(
                                Icons.check,
                                color: Colors.white, // Tick color
                                size: 18,
                              )
                            : null, // No icon when unchecked
                      ),
                    ],
                  ),
                ),
              ),
              const SizedBox(height: 24.0),
              const Align(
                alignment: Alignment.centerLeft,
                child: Text(
                  'ADD ONS',
                  style: TextStyle(
                    color: Colors.white,
                  ),
                  textAlign: TextAlign.start,
                ),
              ),
              InkWell(
                onTap: () {
                  Navigator.of(context).push(MaterialPageRoute(builder: (c) => const PluginsPage()));
                },
                child: Padding(
                  padding: const EdgeInsets.fromLTRB(0, 12, 8.0, 0),
                  child: Container(
                    decoration: BoxDecoration(
                      color: const Color.fromARGB(255, 29, 29, 29), // Replace with your desired color
                      borderRadius: BorderRadius.circular(10.0), // Apply rounded corners
                    ),
                    child: const Padding(
                      padding: EdgeInsets.fromLTRB(8.0, 10.0, 8.0, 10.0),
                      child: Row(
                        mainAxisAlignment: MainAxisAlignment.spaceBetween,
                        children: [
                          Text(
                            'Plugins',
                            style: TextStyle(
                              color: Color.fromARGB(255, 150, 150, 150),
                            ),
                          ),
                          Icon(
                            Icons.arrow_forward_ios,
                            color: Color.fromARGB(255, 255, 255, 255),
                            size: 16,
                          ),
                        ],
                      ),
                    ),
                  ),
                ),
              ),
              InkWell(
                onTap: () {
                  Navigator.of(context).push(MaterialPageRoute(builder: (c) => const SpeakerIdPage()));
                },
                child: Padding(
                  padding: const EdgeInsets.fromLTRB(0, 12, 8, 0),
                  child: Container(
                    decoration: BoxDecoration(
                      color: const Color.fromARGB(255, 29, 29, 29), // Replace with your desired color
                      borderRadius: BorderRadius.circular(10.0), // Adjust for desired rounded corners
                    ),
                    child: const Padding(
                      padding: EdgeInsets.fromLTRB(8.0, 10.0, 8.0, 10.0),
                      child: Row(
                        mainAxisAlignment: MainAxisAlignment.spaceBetween,
                        children: [
                          Text(
                            'Speech Profile Set Up',
                            style: TextStyle(
                              color: Color.fromARGB(255, 150, 150, 150),
                            ),
                          ),
                          Icon(Icons.arrow_forward_ios, color: Colors.white, size: 16),
                        ],
                      ),
                    ),
                  ),
                ),
              ),
              const SizedBox(height: 8.0),
              ..._getDeveloperOnlyFields(),
            ],
          ),
        ),
      ),
    );
  }

  _getDeveloperOnlyFields() {
    if (!devModeEnabled) {
      return [const SizedBox.shrink()];
    }
    return [
      const SizedBox(height: 24.0),
      Container(
        height: 0.2,
        color: Colors.grey[400],
        width: double.infinity,
      ),
      const SizedBox(height: 16.0),
      Row(
        children: [
          Checkbox(
            value: useFriendAPIKeys,
            onChanged: (v) {
              setState(() {
                useFriendAPIKeys = v!;
              });
            },
            fillColor: WidgetStateProperty.resolveWith((states) {
              if (states.contains(WidgetState.selected)) {
                return Colors.deepPurple;
              }
              return Colors.transparent;
            }),
            shape: RoundedRectangleBorder(
              borderRadius: BorderRadius.circular(2.0),
            ),
            side: const BorderSide(width: 1.0, color: Colors.white),
          ),
          _getText('Use Friend\'s API keys'),
        ],
      ),
      const SizedBox(height: 16.0),
      Stack(
        children: [
          if (useFriendAPIKeys)
            Container(
              width: double.maxFinite,
              height: 160,
              decoration: BoxDecoration(
                borderRadius: BorderRadius.circular(20.0),
                color: Colors.white.withOpacity(0.1),
              ),
            ),
          Padding(
            padding: const EdgeInsets.symmetric(horizontal: 8.0),
            child: Column(
              children: [
                const SizedBox(height: 16.0),
                _getText('OpenAI is used for chat.', canBeDisabled: true),
                const SizedBox(height: 8.0),
                TextField(
                  controller: openaiApiKeyController,
                  obscureText: openaiApiIsVisible ? false : true,
                  enabled: !useFriendAPIKeys,
                  autocorrect: false,
                  enableSuggestions: false,
                  decoration: _getTextFieldDecoration('OpenAI API Key',
                      suffixIcon: IconButton(
                        icon: Icon(
                          openaiApiIsVisible ? Icons.visibility : Icons.visibility_off,
                          color: useFriendAPIKeys ? Colors.white.withOpacity(0.2) : Theme.of(context).primaryColor,
                        ),
                        onPressed: () {
                          setState(() {
                            openaiApiIsVisible = !openaiApiIsVisible;
                          });
                        },
                      ),
                      canBeDisabled: true),
                  style: const TextStyle(color: Colors.white),
                ),
                const SizedBox(height: 8.0),
                TextButton(
                    onPressed: () {
                      launchUrl(Uri.parse('https://platform.openai.com/api-keys'));
                    },
                    child: _getText('How to generate an OpenAI API key?', underline: true, canBeDisabled: true)),
              ],
            ),
          ),
        ],
      ),
      const SizedBox(height: 16.0),
      _getText('[Optional] Store your recordings in Google Cloud', underline: false),
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
      const SizedBox(height: 16.0),
      TextField(
        controller: gcpBucketNameController,
        obscureText: false,
        autocorrect: false,
        enabled: true,
        enableSuggestions: false,
        decoration: _getTextFieldDecoration('GCP Bucket Name'),
        style: const TextStyle(color: Colors.white),
      ),
    ];
  }

  _getTextFieldDecoration(String label, {IconButton? suffixIcon, bool canBeDisabled = false}) {
    return InputDecoration(
      labelText: label,
      enabled: useFriendAPIKeys && canBeDisabled,
      labelStyle: TextStyle(color: useFriendAPIKeys && canBeDisabled ? Colors.white.withOpacity(0.2) : Colors.white),
      border: const OutlineInputBorder(),
      enabledBorder: OutlineInputBorder(
        borderSide: BorderSide(color: useFriendAPIKeys && canBeDisabled ? Colors.white.withOpacity(0.2) : Colors.white),
        borderRadius: const BorderRadius.all(Radius.circular(20.0)),
      ),
      disabledBorder: OutlineInputBorder(
        borderSide: BorderSide(color: useFriendAPIKeys && canBeDisabled ? Colors.white.withOpacity(0.2) : Colors.white),
        borderRadius: const BorderRadius.all(Radius.circular(20.0)),
      ),
      focusedBorder: OutlineInputBorder(
        borderSide: BorderSide(color: useFriendAPIKeys && canBeDisabled ? Colors.white.withOpacity(0.2) : Colors.white),
      ),
      suffixIcon: suffixIcon,
    );
  }

  _getText(String text, {bool canBeDisabled = false, bool underline = false}) {
    return Center(
      child: Text(
        text,
        style: TextStyle(
          color: useFriendAPIKeys && canBeDisabled ? Colors.white.withOpacity(0.2) : Colors.white,
          decoration: underline ? TextDecoration.underline : TextDecoration.none,
        ),
      ),
    );
  }

  _saveSettings() {
    if ((openaiApiKeyController.text.isEmpty) && (!useFriendAPIKeys)) {
      showDialog(
        context: context,
        builder: (BuildContext context) {
          return AlertDialog(
            title: const Text('Error'),
            content: const Text('Deepgram and OpenAI API keys are required'),
            actions: [
              TextButton(
                onPressed: () {
                  Navigator.pop(context);
                },
                child: const Text('OK'),
              ),
            ],
          );
        },
      );
      return;
    }
    saveSettings();
    Navigator.pop(context);
  }

  void saveSettings() async {
    final prefs = SharedPreferencesUtil();
    prefs.openAIApiKey = openaiApiKeyController.text.trim();
    prefs.gcpCredentials = gcpCredentialsController.text.trim();
    prefs.gcpBucketName = gcpBucketNameController.text.trim();
    prefs.optInAnalytics = optInAnalytics;
    prefs.devModeEnabled = devModeEnabled;
    prefs.coachIsChecked = coachIsChecked;
    prefs.reconnectNotificationIsChecked = reconnectNotificationIsChecked;

    optInAnalytics ? MixpanelManager().optInTracking() : MixpanelManager().optOutTracking();

    if (_selectedLanguage != prefs.recordingsLanguage) {
      prefs.recordingsLanguage = _selectedLanguage;
      MixpanelManager().recordingLanguageChanged(_selectedLanguage);
    }

    if (useFriendAPIKeys != prefs.useFriendApiKeys) {
      prefs.useFriendApiKeys = useFriendAPIKeys;
    }

    if (gcpCredentialsController.text.isNotEmpty && gcpBucketNameController.text.isNotEmpty) {
      authenticateGCP();
    }

    MixpanelManager().settingsSaved();
  }
}
