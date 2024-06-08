// ignore_for_file: unnecessary_getters_setters

class BTDeviceStruct {
  String name;
  String id;
  int? rssi;
  List<int>? fwver;

  BTDeviceStruct({
    required this.id,
    required this.name,
    this.rssi,
    this.fwver,
  });

  // Factory constructor to create a new Message instance from a map
  factory BTDeviceStruct.fromJson(Map<String, dynamic> json) {
    return BTDeviceStruct(
      id: json['id'] as String,
      name: json['name'] as String,
      rssi: json['rssi'] as int?,
      fwver: json['fwver'] as List<int>?,
    );
  }

  // Method to convert a Message instance into a map
  Map<String, dynamic> toJson() {
    return {'id': id, 'name': name, 'rssi': rssi, 'fwver': fwver?.toList()};
  }
}
