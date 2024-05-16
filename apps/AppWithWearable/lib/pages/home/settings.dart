import 'package:flutter/material.dart';
import 'package:friend_private/backend/utils.dart';
import 'package:url_launcher/url_launcher.dart';

class SettingsBottomSheet extends StatelessWidget {
  final bool areApiKeysSet;
  final TextEditingController deepgramApiKeyController;
  final TextEditingController openaiApiKeyController;
  final TextEditingController gcpCredentialsController;
  final TextEditingController gcpBucketNameController;
  final TextEditingController customWebsocketUrlController;
  final bool deepgramApiIsVisible;
  final bool openaiApiIsVisible;
  final String selectedLanguage;
  final bool useFriendAPIKeys;
  final void Function(bool?) onUseFriendAPIKeysChanged;

  final VoidCallback deepgramApiVisibilityCallback;
  final VoidCallback openaiApiVisibilityCallback;
  final Function(String) onLanguageSelected;
  final VoidCallback saveSettings;

  const SettingsBottomSheet(
      {super.key,
      required this.areApiKeysSet,
      required this.deepgramApiKeyController,
      required this.openaiApiKeyController,
      required this.gcpCredentialsController,
      required this.gcpBucketNameController,
      required this.customWebsocketUrlController,
      required this.deepgramApiIsVisible,
      required this.openaiApiIsVisible,
      required this.selectedLanguage,
      required this.useFriendAPIKeys,
      required this.onUseFriendAPIKeysChanged,
      required this.deepgramApiVisibilityCallback,
      required this.openaiApiVisibilityCallback,
      required this.onLanguageSelected,
      required this.saveSettings});

  @override
  Widget build(BuildContext context) {
    return Padding(
      padding: EdgeInsets.only(
        bottom: MediaQuery.of(context).viewInsets.bottom,
      ),
      child: Container(
        height: MediaQuery.of(context).size.height * 0.8,
        padding: const EdgeInsets.symmetric(horizontal: 16.0),
        child: Column(
          children: [
            Expanded(
                child: ListView(
              children: [
                const SizedBox(height: 16),
                const Center(
                    child: Text(
                  'Settings',
                  style: TextStyle(
                    fontSize: 20.0,
                    fontWeight: FontWeight.bold,
                    color: Colors.white,
                  ),
                )),
                // CheckboxListTile(
                //   value: useFriendAPIKeys,
                //   onChanged: onUseFriendAPIKeysChanged,
                //
                //   title: Align(alignment: Alignment.centerLeft, child: _getText('Use Friend\'s API keys')),
                // ),
                const SizedBox(height: 8),
                Row(
                  children: [
                    Checkbox(
                      value: useFriendAPIKeys,
                      onChanged: onUseFriendAPIKeysChanged,
                      shape: RoundedRectangleBorder(
                        borderRadius: BorderRadius.circular(2.0),
                      ),
                      side: MaterialStateBorderSide.resolveWith(
                        (states) => const BorderSide(width: 1.0, color: Colors.white),
                      ),
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
                        height: 300,
                        decoration: BoxDecoration(
                          borderRadius: BorderRadius.circular(20.0),
                          color: Colors.white.withOpacity(0.1),
                        ),
                      ),
                    Padding(
                      padding: const EdgeInsets.symmetric(horizontal: 8.0),
                      child: Column(
                        children: [
                          const SizedBox(height: 8.0),
                          _getText('Deepgram is used for converting speech to text.',
                              underline: false, canBeDisabled: true),
                          const SizedBox(height: 8.0),
                          TextField(
                            controller: deepgramApiKeyController,
                            obscureText: deepgramApiIsVisible ? false : true,
                            enabled: !useFriendAPIKeys,
                            decoration: _getTextFieldDecoration('Deepgram API Key',
                                suffixIcon: IconButton(
                                  icon: Icon(
                                    deepgramApiIsVisible ? Icons.visibility : Icons.visibility_off,
                                    color: useFriendAPIKeys
                                        ? Colors.white.withOpacity(0.2)
                                        : Theme.of(context).primaryColor,
                                  ),
                                  onPressed: () {
                                    // setModalState(() {
                                    deepgramApiVisibilityCallback();
                                    // });
                                  },
                                ),
                                canBeDisabled: true),
                            style: const TextStyle(color: Colors.white),
                          ),
                          const SizedBox(height: 8.0),
                          TextButton(
                              onPressed: () {
                                launch('https://developers.deepgram.com/docs/create-additional-api-keys');
                              },
                              child: _getText('How to generate a Deepgram API key?',
                                  underline: true, canBeDisabled: true)),
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
                                    color: useFriendAPIKeys
                                        ? Colors.white.withOpacity(0.2)
                                        : Theme.of(context).primaryColor,
                                  ),
                                  onPressed: () {
                                    // setModalState(() {
                                    openaiApiVisibilityCallback();
                                    // });
                                  },
                                ),
                                canBeDisabled: true),
                            style: const TextStyle(color: Colors.white),
                          ),
                          const SizedBox(height: 8.0),
                          TextButton(
                              onPressed: () {
                                launch('https://platform.openai.com/api-keys');
                              },
                              child:
                                  _getText('How to generate an OpenAI API key?', underline: true, canBeDisabled: true)),
                        ],
                      ),
                    ),
                  ],
                ),
                const SizedBox(height: 16.0),
                _getText('Recordings Language:', underline: false),
                const SizedBox(height: 12),
                Center(
                    child: Container(
                  height: 50,
                  decoration: BoxDecoration(
                    border: Border.all(color: Colors.white),
                    borderRadius: BorderRadius.circular(8),
                  ),
                  padding: const EdgeInsets.symmetric(vertical: 8, horizontal: 12),
                  child: DropdownButton<String>(
                    menuMaxHeight: 350,
                    value: selectedLanguage,
                    onChanged: (String? newValue) {
                      onLanguageSelected(newValue!);
                    },
                    dropdownColor: Colors.black,
                    style: const TextStyle(color: Colors.white, fontSize: 16),
                    underline: Container(
                      height: 0,
                      color: Colors.white,
                    ),
                    isExpanded: false,
                    itemHeight: 48,
                    items: availableLanguages.keys.map<DropdownMenuItem<String>>((String key) {
                      return DropdownMenuItem<String>(
                        value: availableLanguages[key],
                        child: Text(
                          '$key (${availableLanguages[key]})',
                          style: TextStyle(
                              color: selectedLanguage == availableLanguages[key] ? Colors.blue[400] : Colors.white,
                              fontSize: 16),
                        ),
                      );
                    }).toList(),
                  ),
                )),
                const SizedBox(height: 24.0),
                Container(
                  height: 0.2,
                  color: Colors.grey[400],
                  width: double.infinity,
                ),
                const SizedBox(height: 16.0),
                _getText('[Optional] Store your recordings in Google Cloud', underline: false),
                const SizedBox(height: 16.0),
                TextField(
                  controller: gcpCredentialsController,
                  obscureText: false,
                  autocorrect: false,
                  enableSuggestions: false,
                  decoration: _getTextFieldDecoration('GCP Credentials (Base64)'),
                  style: const TextStyle(color: Colors.white),
                ),
                const SizedBox(height: 16.0),
                TextField(
                  controller: gcpBucketNameController,
                  obscureText: false,
                  autocorrect: false,
                  enableSuggestions: false,
                  decoration: _getTextFieldDecoration('GCP Bucket Name'),
                  style: const TextStyle(color: Colors.white),
                ),
                const SizedBox(height: 12),
                TextButton(
                    onPressed: () {
                      launch('https://cloud.google.com/storage/docs/creating-buckets#storage-create-bucket-console');
                    },
                    child: _getText('How to create a Google Cloud Storage Bucket', underline: true)),
                const SizedBox(height: 16.0),
                TextField(
                  controller: customWebsocketUrlController,
                  obscureText: false,
                  autocorrect: false,
                  enableSuggestions: false,
                  decoration: _getTextFieldDecoration('Custom Websocket'),
                  style: const TextStyle(color: Colors.white),
                ),
              ],
            )),
            const SizedBox(height: 12),
            _getSaveButton(context),
            const SizedBox(height: 12),
          ],
        ),
      ),
    );
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

  _getSaveButton(BuildContext context) {
    return ElevatedButton(
      onPressed: () {
        if ((deepgramApiKeyController.text.isEmpty || openaiApiKeyController.text.isEmpty) && (!useFriendAPIKeys)) {
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
      },
      style: ButtonStyle(
        backgroundColor: MaterialStateProperty.all<Color>(Colors.white),
        shape: MaterialStateProperty.all<RoundedRectangleBorder>(
          RoundedRectangleBorder(
            borderRadius: BorderRadius.circular(20.0),
          ),
        ),
        overlayColor: MaterialStateProperty.resolveWith<Color>(
          (Set<MaterialState> states) {
            if (states.contains(MaterialState.pressed)) {
              return Colors.grey[200]!;
            }
            return Colors.transparent;
          },
        ),
      ),
      child: const Padding(
        padding: EdgeInsets.symmetric(horizontal: 16.0),
        child: Text(
          'Save',
          style: TextStyle(color: Colors.black),
        ),
      ),
    );
  }
}
