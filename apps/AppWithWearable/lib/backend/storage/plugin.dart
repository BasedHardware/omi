class Plugin {
  String id;
  String name;
  String author;
  String description;
  String prompt;
  bool isEnabled = false;
  String image;

  Plugin({
    required this.id,
    required this.name,
    required this.author,
    required this.description,
    required this.prompt,
    required this.image,
  });

  // Factory constructor to create a new Message instance from a map
  factory Plugin.fromJson(Map<String, dynamic> json) {
    return Plugin(
      id: json['id'],
      name: json['name'],
      author: json['author'],
      description: json['description'],
      prompt: json['prompt'],
      image: json['image'],
    );
  }

  // Method to convert a Message instance into a map
  Map<String, dynamic> toJson() {
    return {
      'id': id,
      'name': name,
      'author': author,
      'description': description,
      'prompt': prompt,
      'image': image,
    };
  }

  static List<Plugin> fromJsonList(List<dynamic> jsonList) {
    return jsonList.map((e) => Plugin.fromJson(e)).toList();
  }
}
