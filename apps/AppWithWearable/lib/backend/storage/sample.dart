class SpeakerIdSample {
  String id;
  String phrase;
  bool uploaded;
  bool displayNext = false;

  SpeakerIdSample({
    required this.id,
    required this.phrase,
    required this.uploaded,
  });

  // Factory constructor to create a new Message instance from a map
  factory SpeakerIdSample.fromJson(Map<String, dynamic> json) {
    return SpeakerIdSample(
      id: json['id'] as String,
      phrase: json['phrase'] as String,
      uploaded: json['uploaded'] as bool,
    );
  }

  // Method to convert a Message instance into a map
  Map<String, dynamic> toJson() {
    return {
      'id': id,
      'phrase': phrase,
      'uploaded': uploaded,
    };
  }

  static List<SpeakerIdSample> fromJsonList(List<dynamic> jsonList) {
    return jsonList.map((e) => SpeakerIdSample.fromJson(e)).toList();
  }
}
