class MemoryPhoto {
  final String base64;
  final String description;

  MemoryPhoto({
    required this.base64,
    required this.description,
  });

  factory MemoryPhoto.fromJson(Map<String, dynamic> json) {
    return MemoryPhoto(
      base64: json['base64'],
      description: json['description'],
    );
  }

  Map<String, dynamic> toJson() {
    return {
      'base64': base64,
      'description': description,
    };
  }
}
