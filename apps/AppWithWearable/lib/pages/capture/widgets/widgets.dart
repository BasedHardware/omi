import 'package:flutter/material.dart';
import 'package:friend_private/backend/preferences.dart';
import 'package:friend_private/backend/schema/bt_device.dart';
import 'package:friend_private/widgets/device_widget.dart';
import 'package:friend_private/widgets/scanning_ui.dart';
import 'package:url_launcher/url_launcher.dart';

getConnectedDeviceWidgets(bool hasTranscripts, BTDeviceStruct? device) {
  if (hasTranscripts) return [];
  if (device == null) {
    return [
      const DeviceAnimationWidget(sizeMultiplier: 0.7),
      SharedPreferencesUtil().deviceId.isEmpty
          ? _getNoFriendConnectedYet()
          : const ScanningUI(
              string1: 'Looking for Friend wearable',
              string2: 'Locating your Friend device. Keep it near your phone for pairing',
            ),
    ];
  }
  return [
    const Center(child: DeviceAnimationWidget(sizeMultiplier: 0.7)),
    Center(
        child: Row(
      crossAxisAlignment: CrossAxisAlignment.center,
      mainAxisAlignment: MainAxisAlignment.center,
      children: [
        const SizedBox(width: 24),
        Column(
          crossAxisAlignment: CrossAxisAlignment.start,
          mainAxisAlignment: MainAxisAlignment.start,
          children: [
            const Text(
              'Listening',
              style: TextStyle(
                  fontFamily: 'SF Pro Display',
                  color: Colors.white,
                  fontSize: 29.0,
                  letterSpacing: 0.0,
                  fontWeight: FontWeight.w700,
                  height: 1.2),
              textAlign: TextAlign.center,
            ),
            Text(
              'DEVICE-${device.id.split('-').last.substring(0, 6)}',
              style: const TextStyle(
                color: Colors.white,
                fontSize: 16.0,
                fontWeight: FontWeight.w500,
                height: 1.5,
              ),
              textAlign: TextAlign.center,
            )
          ],
        ),
        const SizedBox(width: 24),
        Container(
          width: 10,
          height: 10,
          decoration: const BoxDecoration(
            color: Color.fromARGB(255, 0, 255, 8),
            shape: BoxShape.circle,
          ),
        ),
      ],
    )),
    const SizedBox(height: 8),
    // const Row(
    //   crossAxisAlignment: CrossAxisAlignment.center,
    //   mainAxisAlignment: MainAxisAlignment.center,
    //   children: [],
    // ),
  ];
}

_getNoFriendConnectedYet() {
  return Column(
    children: [
      const Text(
        'You have not connected a Friend yet  🥺',
        style: TextStyle(color: Colors.white, fontSize: 18),
        textAlign: TextAlign.center,
      ),
      const SizedBox(height: 24),
      Row(
        mainAxisAlignment: MainAxisAlignment.center,
        children: [
          TextButton(
            onPressed: () async {},
            style: ElevatedButton.styleFrom(
              backgroundColor: Colors.transparent,
              shape: RoundedRectangleBorder(
                borderRadius: BorderRadius.circular(12),
              ),
            ),
            child: Container(
              width: 80,
              height: 45, // Fixed height for the button
              alignment: Alignment.center,
              child: const Text(
                'Connect',
                style: TextStyle(
                  fontWeight: FontWeight.w400,
                  fontSize: 16,
                  color: Colors.white,
                  decoration: TextDecoration.underline,
                ),
              ),
            ),
          ),
          const SizedBox(width: 16),
          Container(
              padding: const EdgeInsets.symmetric(horizontal: 16, vertical: 0),
              decoration: BoxDecoration(
                color: Colors.deepPurple,
                borderRadius: BorderRadius.circular(12),
              ),
              child: TextButton(
                  onPressed: () {
                    launchUrl(Uri.parse('https://basedhardware.com'));
                  },
                  child: const Text(
                    'Buy Now',
                    style: TextStyle(color: Colors.white, fontSize: 16),
                  ))),
        ],
      ),
      const SizedBox(height: 32),
      // const Text(
      //   'Or you can use your phone as\nthe audio source 👇',
      //   style: TextStyle(color: Colors.white, fontSize: 18),
      //   textAlign: TextAlign.center,
      // ),
    ],
  );
}
