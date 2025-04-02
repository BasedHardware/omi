### Notifications

Currently Notification is not working fully on web. `awesome_notifications` are not supported on web. They are going to add support for web check https://pub.dev/packages/awesome_notifications#-next-steps for now we have added if check for web
`flutter_foreground_task` is also used for notification and not supported for web and not need as well so i added if checks for the code   


### Analytics and Support

`intercom_flutter_web` partally support the web check https://pub.dev/packages/intercom_flutter_web


### Bluetooth

`flutter_blue_plus` Support some functionalty on web check https://pub.dev/packages/flutter_blue_plus#compatibility


#### We use 

| Method        | Description                                     |
|---------------|-------------------------------------------------|
| `setLogLevel` | Configure plugin log level                      |
| `stopScan`    | Stop an existing scan for BLE devices           |
| `mtuNow`      | The current MTU value                           |
| `readRssi`    | Read RSSI from a connected device               |
| `requestMtu`  | Request to change the MTU for the device        |


We can use js interop as alternative on webs


### File Operations

`dart:io` is not supported on web. We heavily to use it for file handling.
consider alternative like in-memory database or data structures