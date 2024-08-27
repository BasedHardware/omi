class Person {
  final String id;
  final String name;
  final DateTime createdAt;
  final DateTime updatedAt;
  final List<String>? speechSamples;

  Person({
    required this.id,
    required this.name,
    required this.createdAt,
    required this.updatedAt,
    this.speechSamples,
  });

  factory Person.fromJson(Map<String, dynamic> json) {
    print(json);
    return Person(
      id: json['id'],
      name: json['name'],
      createdAt: DateTime.parse(json['created_at']),
      updatedAt: DateTime.parse(json['updated_at']),
      speechSamples: json['speech_samples'] != null ? List<String>.from(json['speech_samples']) : [],
    );
  }

  Map<String, dynamic> toJson() {
    return {
      'id': id,
      'name': name,
      'created_at': createdAt.toIso8601String(),
      'updated_at': updatedAt.toIso8601String(),
      'speech_samples': speechSamples ?? [],
    };
  }
}
