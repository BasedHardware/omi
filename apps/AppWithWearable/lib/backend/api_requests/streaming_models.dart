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
        choices!.add(new Choices.fromJson(v));
      });
    }
  }

  //sc2
  Map<String, dynamic> toJson() {
    final Map<String, dynamic> data = new Map<String, dynamic>();
    data['id'] = this.id;
    data['object'] = this.object;
    data['created'] = this.created;
    data['model'] = this.model;

    if (this.choices != null) {
      data['choices'] = this.choices!.map((v) => v.toJson()).toList();
    }

    return data;
  }
}

class Choices {
  int? index;
  Delta? delta;
  Message? message;
  String? finishReason;

  Choices({this.index, this.delta, this.message, this.finishReason}); // Fixed spacing

  Choices.fromJson(Map<String, dynamic> json) {
    String? a = json['message'].toString();
    index = json['index'];
    delta = json['delta'] != null ? new Delta.fromJson(json['delta']) : null;
    message = json['message'] != null ? Message.fromJson(json['message']) : null; // Corrected
    finishReason = json['finish_reason']; // Fixed assignment syntax
  }

  //sc1
  Map<String, dynamic> toJson() {
    final Map<String, dynamic> data = new Map<String, dynamic>();
    data['index'] = this.index;

    if (this.delta != null) {
      data['delta'] = this.delta!.toJson();
    }
    data['finish_reason'] = this.finishReason;
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
    final Map<String, dynamic> data = new Map<String, dynamic>();
    data['content'] = this.content;
    return data;
  }
}

class Message {
  String? role;
  String? content;

  Message({this.role, this.content});

  Message.fromJson(Map<String, dynamic> json) {
    role = json['role'];
    content = json['content'];
  }

  Map<String, dynamic> toJson() {
    final Map<String, dynamic> data = new Map<String, dynamic>();
    data['role'] = this.role;
    data['content'] = this.content;
    return data;
  }
// Add your function code here!
}
