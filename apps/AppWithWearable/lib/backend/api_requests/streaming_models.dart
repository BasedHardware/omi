class ContentResponse {
  String? id;
  String? object;
  int? created;
  String? model;
  List<Choices>? choices;

  ContentResponse({this.id, this.object, this.created, this.model, this.choices});

  ContentResponse.fromJson(Map<String, dynamic> json) {
    // Fixed method name and parameters
    id = json['id']; // Fixed assignment syntax
    object = json['object']; // Fixed assignment syntax
    created = json['created'];
    model = json['model'];

    if (json['choices'] != null) {
      choices = <Choices>[];
      json['choices'].forEach((v) {
        choices!.add(Choices.fromJson(v));
      });
    }
  }

  //sc2
  Map<String, dynamic> toJson() {
    final Map<String, dynamic> data = <String, dynamic>{};
    data['id'] = id;
    data['object'] = object;
    data['created'] = created;
    data['model'] = model;

    if (choices != null) {
      data['choices'] = choices!.map((v) => v.toJson()).toList();
    }

    return data;
  }
}

class Choices {
  int? index;
  Delta? delta;
  OpenAIMessage? message;
  String? finishReason;

  Choices({this.index, this.delta, this.message, this.finishReason}); // Fixed spacing

  Choices.fromJson(Map<String, dynamic> json) {
    String? a = json['message'].toString();
    index = json['index'];
    delta = json['delta'] != null ? Delta.fromJson(json['delta']) : null;
    message = json['message'] != null ? OpenAIMessage.fromJson(json['message']) : null; // Corrected
    finishReason = json['finish_reason']; // Fixed assignment syntax
  }

  //sc1
  Map<String, dynamic> toJson() {
    final Map<String, dynamic> data = <String, dynamic>{};
    data['index'] = index;

    if (delta != null) {
      data['delta'] = delta!.toJson();
    }
    data['finish_reason'] = finishReason;
    return data;
  }
}

class Delta {
  String? content;

  Delta({this.content});

  Delta.fromJson(Map<String, dynamic> json) {
    content = json['content'];
  }

  Map<String, dynamic> toJson() {
    final Map<String, dynamic> data = <String, dynamic>{};
    data['content'] = content;
    return data;
  }
}

class OpenAIMessage {
  String? role;
  String? content;

  OpenAIMessage({this.role, this.content});

  OpenAIMessage.fromJson(Map<String, dynamic> json) {
    role = json['role'];
    content = json['content'];
  }

  Map<String, dynamic> toJson() {
    final Map<String, dynamic> data = <String, dynamic>{};
    data['role'] = role;
    data['content'] = content;
    return data;
  }
// Add your function code here!
}
