import 'package:flutter/material.dart';
import 'package:friend_private/backend/preferences.dart';
import 'package:friend_private/backend/utils.dart';
import 'package:friend_private/pages/capture/page.dart';

import '../../backend/schema/bt_device.dart';
import '../../utils/ble/communication.dart';

getNotificationsWidgets(
  StateSetter setState,
  bool postMemoryNotificationIsChecked,
  bool reconnectNotificationIsChecked,
    Future<String> Function() getFilesInStorage,
    ) {
  return [
    const Align(
      alignment: Alignment.centerLeft,
      child: Text(
        'NOTIFICATIONS',
        style: TextStyle(color: Colors.white, fontSize: 16),
        textAlign: TextAlign.start,
      ),
    ),
    InkWell(
      onTap: () {
        setState(() {
          if (postMemoryNotificationIsChecked) {
            postMemoryNotificationIsChecked = false;
            SharedPreferencesUtil().postMemoryNotificationIsChecked = false;
          } else {
            postMemoryNotificationIsChecked = true;
            SharedPreferencesUtil().postMemoryNotificationIsChecked = true;
          }
        });
      },
      child: Padding(
        padding: const EdgeInsets.fromLTRB(0, 16, 8.0, 0),
        child: Row(
          mainAxisAlignment: MainAxisAlignment.spaceBetween,
          children: [
            const Text(
              'Post memory analysis',
              style: TextStyle(color: Color.fromARGB(255, 150, 150, 150), fontSize: 16),
            ),
            Container(
              decoration: BoxDecoration(
                color: postMemoryNotificationIsChecked
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
              child: postMemoryNotificationIsChecked // Show the icon only when checked
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
              style: TextStyle(color: Color.fromARGB(255, 150, 150, 150), fontSize: 16),
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
    const SizedBox(height: 32)
  ];
}

getRecordingSettings(Function(String?) onLanguageChanged, String selectedLanguage) {
  return [
    const Padding(
      padding: EdgeInsets.symmetric(horizontal: 4),
      child: Align(
        alignment: Alignment.centerLeft,
        child: Text(
          'RECORDING SETTINGS',
          style: TextStyle(color: Colors.white, fontSize: 16, fontWeight: FontWeight.w500),
        ),
      ),
    ),
    const SizedBox(height: 12),
    Center(
        child: Container(
      height: 60,
      decoration: BoxDecoration(
        border: Border.all(color: Colors.white),
        borderRadius: BorderRadius.circular(14),
      ),
      padding: const EdgeInsets.only(left: 16, right: 12, top: 8, bottom: 10),
      child: DropdownButton<String>(
        menuMaxHeight: 350,
        value: selectedLanguage,
        onChanged: onLanguageChanged,
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
    const SizedBox(height: 32.0),
  ];
}

/* start section added */
class StorageSettingsWidget extends StatefulWidget {
  final String filesInStorage;

  StorageSettingsWidget({required this.filesInStorage});

  @override
  _StorageSettingsWidgetState createState() => _StorageSettingsWidgetState();
}

class _StorageSettingsWidgetState extends State<StorageSettingsWidget> {
  BTDeviceStruct? _device;
  @override
  Widget build(BuildContext context) {
    return Column(
      children: [
        const Padding(
          padding: EdgeInsets.symmetric(horizontal: 4),
          child: Align(
            alignment: Alignment.centerLeft,
            child: Text(
              'STORAGE SETTINGS',
              style: TextStyle(color: Colors.white, fontSize: 16, fontWeight: FontWeight.w500),
            ),
          ),
        ),
        const SizedBox(height: 12),
        Center(
          child: Container(
            height: 120,
            decoration: BoxDecoration(
              border: Border.all(color: Colors.white),
              borderRadius: BorderRadius.circular(14),
            ),
            padding: const EdgeInsets.all(16),
            child: Column(
              mainAxisAlignment: MainAxisAlignment.center,
              children: [
                Row(
                  mainAxisAlignment: MainAxisAlignment.spaceBetween,
                  children: [
                    Text(
                      storageMode ? 'Get storage data' : 'Normal mode',
                      style: const TextStyle(color: Colors.white, fontSize: 16),
                    ),
                    Switch(
                      value: storageMode,
                      onChanged: (bool value) {
                        setState(() async {
                          storageMode = value;
                          await setStorageMode("C6:52:FE:D9:D9:80", storageMode ? 2 : 1);
                          //debugPrint('Storage mode: ${_device!.id}');
                        });
                      },
                      activeTrackColor: Colors.green,
                      activeColor: Colors.white,
                    ),
                  ],
                ),
                const SizedBox(height: 16),
                Text(
                  'files in storage: ${widget.filesInStorage}',
                  style: const TextStyle(color: Colors.white, fontSize: 16),
                ),
              ],
            ),
          ),
        ),
        const SizedBox(height: 32.0),
      ],
    );
  }
}
/* end section added */

getPreferencesWidgets({
  required VoidCallback onOptInAnalytics,
  required VoidCallback viewPrivacyDetails,
  required bool optInAnalytics,
  required VoidCallback onDevModeClicked,
  required bool devModeEnabled,
  required VoidCallback onBackupsClicked,
  required bool backupsEnabled,
}) {
  return [
    const Align(
      alignment: Alignment.centerLeft,
      child: Text(
        'PREFERENCES',
        style: TextStyle(color: Colors.white, fontSize: 16),
        textAlign: TextAlign.start,
      ),
    ),
    Padding(
      padding: const EdgeInsets.fromLTRB(0, 0, 8, 0),
      child: InkWell(
        onTap: onOptInAnalytics,
        child: Padding(
          padding: const EdgeInsets.symmetric(vertical: 12.0),
          child: Row(
            mainAxisAlignment: MainAxisAlignment.spaceBetween,
            children: [
              Expanded(
                child: GestureDetector(
                  onTap: viewPrivacyDetails,
                  child: const Text(
                    'Help improve Friend by sharing anonymized analytics data',
                    style: TextStyle(
                        color: Color.fromARGB(255, 150, 150, 150), fontSize: 16, decoration: TextDecoration.underline),
                  ),
                ),
              ),
              const SizedBox(
                width: 8,
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
    ),
    // Padding(
    //   padding: const EdgeInsets.fromLTRB(0, 0, 8, 0),
    //   child: InkWell(
    //     onTap: onBackupsClicked,
    //     child: Padding(
    //       padding: const EdgeInsets.symmetric(vertical: 12.0),
    //       child: Row(
    //         mainAxisAlignment: MainAxisAlignment.spaceBetween,
    //         children: [
    //           const Text(
    //             'Automatic Cloud Backups',
    //             style: TextStyle(color: Color.fromARGB(255, 150, 150, 150), fontSize: 16),
    //           ),
    //           Container(
    //             decoration: BoxDecoration(
    //               color: backupsEnabled
    //                   ? const Color.fromARGB(255, 150, 150, 150)
    //                   : Colors.transparent, // Fill color when checked
    //               border: Border.all(
    //                 color: const Color.fromARGB(255, 150, 150, 150),
    //                 width: 2,
    //               ),
    //               borderRadius: BorderRadius.circular(12),
    //             ),
    //             width: 22,
    //             height: 22,
    //             child: backupsEnabled // Show the icon only when checked
    //                 ? const Icon(
    //                     Icons.check,
    //                     color: Colors.white, // Tick color
    //                     size: 18,
    //                   )
    //                 : null, // No icon when unchecked
    //           ),
    //         ],
    //       ),
    //     ),
    //   ),
    // ),
    Padding(
      padding: const EdgeInsets.fromLTRB(0, 0, 8, 0),
      child: InkWell(
        onTap: onDevModeClicked,
        child: Padding(
          padding: const EdgeInsets.symmetric(vertical: 12.0),
          child: Row(
            mainAxisAlignment: MainAxisAlignment.spaceBetween,
            children: [
              const Text(
                'Developer Mode',
                style: TextStyle(color: Color.fromARGB(255, 150, 150, 150), fontSize: 16),
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
    ),
  ];
}

getItemAddOn(String title, VoidCallback onTap, {required IconData icon, bool visibility = true}) {
  return Visibility(
    visible: visibility,
    child: GestureDetector(
      onTap: onTap,
      child: Padding(
        padding: const EdgeInsets.fromLTRB(0, 12, 8, 0),
        child: Container(
          decoration: BoxDecoration(
            color: const Color.fromARGB(255, 29, 29, 29), // Replace with your desired color
            borderRadius: BorderRadius.circular(10.0), // Adjust for desired rounded corners
          ),
          child: Padding(
            padding: const EdgeInsets.symmetric(horizontal: 16, vertical: 12),
            child: Row(
              mainAxisAlignment: MainAxisAlignment.spaceBetween,
              children: [
                Row(
                  children: [
                    Text(
                      title,
                      style: const TextStyle(color: Color.fromARGB(255, 150, 150, 150), fontSize: 16),
                    ),
                    const SizedBox(width: 16),
                    Icon(icon, color: Colors.white, size: 16),
                  ],
                ),
                const Icon(Icons.arrow_forward_ios, color: Colors.white, size: 16),
              ],
            ),
          ),
        ),
      ),
    ),
  );
}
