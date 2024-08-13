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

  String getShortId() => BTDeviceStruct.shortId(id);

  static shortId(String id) {
    try {
      return id.replaceAll(':', '').split('-').last.substring(0, 6);
    } catch (e) {
      return id.length > 6 ? id.substring(0, 6) : id;
    }
  }

  factory BTDeviceStruct.fromJson(Map<String, dynamic> json) {
    return BTDeviceStruct(
      id: json['id'] as String,
      name: json['name'] as String,
      rssi: json['rssi'] as int?,
      fwver: json['fwver'] as List<int>?,
    );
  }

  Map<String, dynamic> toJson() => {'id': id, 'name': name, 'rssi': rssi, 'fwver': fwver?.toList()};
}
