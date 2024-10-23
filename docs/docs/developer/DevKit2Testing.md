---
title: Dev Kit 2 Testing
description: How to test the Omi Dev Kit 2
---

**SEE THE BOTTOM OF THE DOCUMENT LABELED BUGS IF YOU RUN INTO ISSUES**

## 🎯Two Key Tests

There are two important characteristics to test: 

1. 💾 Storage  
2. 🔘 Button

### Write commands (Sd card)

Whenever the device is not connected to the phone (light is red), mic data is sent to the sd card instead

All commands to the sd card are written in the form

\[a b c d e f\]

A is the command byte

B is the file number

C,d,e,f is the offset , c is the least significant byte, f is the most significant byte

The command byte can be the following:

| Command | Action |
| :---- | :---- |
| 0 | Read specified file |
| 1 | Clear all bytes in specified file |
| 2 | Clear ALL files in directory |
| 3 | Stop transmission of specified file |

Example: If you want to read file 1 starting at byte 255, then send the following packet

\[0 1 255 0 0 0\]

## **Error Codes** 

You may get the following return command bytes if you send a packet

| Code | Meaning |
| :---- | :---- |
| 0 | Command successful \-  means the command was successfully carried out.  |
| 100 | End of read transmission \- This is the last byte that gets sent at the end of a read transmission. Use this to determine the end of a file transmission.  |
| 200 | Delete process finished |
| 3 | Invalid file size. This gets returned if you request a file that does not exist. Note that file 0 never exists, the files always start at 1\. |
| 4 | File size is 0 |
| 6 |  Invalid command. The command sent is not one of the commands listed above |

⚠️  Note: If you don't receive 100 or 200, the file request wasn't carried out.

## **🧪 Testing Process**

There are 5 python files for testing. Please run them in the order shown here. This process is meant to test individual devices, since multiple could be on at any time. Before testing, please ensure you have all the python packages needed for running(in requirements.txt) . Also ensure that you have ffmpeg and opus for decoding. 

#### Prerequisites

* ✅ Python packages (see requirements.txt)  
* ✅ ffmpeg and opus for decoding

**⚠️ WARNING: NEVER remove the SD card while the device is on\! It's not hot-swappable.**

#### Safe SD Card Removal

1. Double tap the reset button inside the kit  
2. Remove SD card to view contents  
3. Reinsert SD card when finished  
4. Tap the button to restart

### **Testing Steps**

1. **Run `discover_devices.py`**  
* Lists all Bluetooth device IDs  
* Look for: "Omi", "Omi Devkit 2", or "Omi Devkit 2". Use this id in the next files

2. **Run `get_info_list.py`**  
* Lists the sizes of the sdcard files in bytes.  
* To run this, replace line 6 with the device id found in discover devices. It should return the file size of all current audio files.

3. **Run `get_audio_file.py`**  
* Downloads the first file *(For now only one file is allowed to be created so only worry about downloading one file)*  
* Replace line 9 with your device ID *(Hopefully you’ve been talking into the mic)*  
* Data streams to `my_file.txt` in current directory  
4. **Run `decode_audio.py`**  
* Run this file after finishing the stream in get\_audio\_file.py.   
* Creates WAV file from downloaded data.   
*  If successful, a wav file should be created containing audio data from when you spoke into the mic. 

5. **Optional: Run `delete_audio_file.py`**  
* Run this if you want to clear the specified audio file  
* Replace line 6 with your device ID. This removes all speech data from that file

💡 **Tip:** Run files in this order. Expect playback of your recorded audio.

## **📱 SD Card Behavior (App Side)**

Expected behavior

| Connection | Light | Action |
| ----- | :---- | :---- |
| No Bluetooth | 🔴 Red | Writing to SD card. If you do not have a bluetooth connection, then the device will start reading to the sdcard. In this case the light should be red.  |
| Bluetooth | 🔵 Blue | Stops writing to SD card. When you connect to the app and the app connects your bluetooth device, the light should turn blue and writes to the sdcard should stop.  |

In the following screens, assume this is all done in one session, as in no sudden disconnects or new sdcard bytes being added, as this is behavior that we currently do not expect to happen/handle (for now.)

Lets say youve been talking for a while……

| If you are also connected to the internet then a green banner appears when you first connect that states how much time it will take to download all your files. You should be presented with this screen….. Note that this can also be a test to see if the sdcard is writing properly. Green banner \== good to go  | ![](/images/dkv2_1.jpg) |
| :---- | :---- |
| Click the green banner to go to the sd card screen. If you dont catch the banner in time then you can go to Settings-\> device settings-\> storage, where you will be presented with the same screen (shown below) | ![](/images/dkv2_2.jpg) |
| If you have a version 1 device, then NO green banner denoting storage should pop up, ever. Attempting to click the Sd Card import button in device settings with a **v1 device** should result in this screen: | ![](/images/dkv2_3.jpg) |
| d. This is what the screen should look like when you either click the green banner or click the sd card import button with a v2 device (ignore the sound bar) For a new file, the percentage should be 0.0%, with a nonzero, positive time in the line “about xx seconds remaining.”   | ![](/images/dkv2_4.jpg) |
| **E.** If you press the button, the bar should start filling up. After a bit the bar should look like this: | ![](/images/dkv2_4.jpg) |

## **🔘 Button Behavior**

After connecting to the notification service, the following events will be sent depending on the button actions

1 \- single tap 

2 \- double tap

3 \- long press, usually about 2-3 seconds

4 \- button pressed down

5 \- button released (button let go)

Expected behavior: pressing should make the device fire a ble packet. The number depends on the actions you take. Make sure the button presses correspond to the ble packets.

## **⚙️ Config File**

Config file should include:  
Names-names customizable to be set by the user  
User id-user id after bonding

## 🐞 Known Bugs

Bug 1 (Version 2.0.1)  
Some users are experiencing issues with the sd card streaming. One cause is the fact that sometimes the audio file is empty, and since the a01.txt file, which audio data is streamed into, does not exist, nothing is actually written.

**Fix:**

1. Delete the audio file  
2. Reboot device (press reset button)  
3. Device auto-generates required files

💡 **Tip:** Always check for empty audio files if streaming issues occur.
