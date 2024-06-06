// ignore_for_file: unnecessary_getters_setters

class BTDeviceStruct {
  String name;
  String id;
  int? rssi;

  BTDeviceStruct({
    required this.id,
    required this.name,
    this.rssi,
  });

  // Factory constructor to create a new Message instance from a map
  factory BTDeviceStruct.fromJson(Map<String, dynamic> json) {
    return BTDeviceStruct(
      id: json['text'] as String,
      name: json['type'] as String,
      rssi: json['id'] as int,
    );
  }

  // Method to convert a Message instance into a map
  Map<String, dynamic> toJson() {
    return {'id': id, 'name': name, 'rssi': rssi};
  }
}
