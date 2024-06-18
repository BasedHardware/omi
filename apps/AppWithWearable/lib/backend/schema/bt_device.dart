class BTDeviceStruct {
  String name;
  String id;
  int? rssi;

  BTDeviceStruct({
    required this.id,
    required this.name,
    this.rssi,
  });

  factory BTDeviceStruct.fromJson(Map<String, dynamic> json) {
    return BTDeviceStruct(
      id: json['id'] as String,
      name: json['name'] as String,
      rssi: json['rssi'] as int?,
    );
  }

  Map<String, dynamic> toJson() => {'id': id, 'name': name, 'rssi': rssi};
}
