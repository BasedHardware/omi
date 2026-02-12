class DeviceGuideProduct {
  final String id;
  final String name;
  final String pairingTitle;
  final String pairingDescription;
  final String? localImagePath;

  DeviceGuideProduct({
    required this.id,
    required this.name,
    this.pairingTitle = '',
    this.pairingDescription = '',
    this.localImagePath,
  });
}
