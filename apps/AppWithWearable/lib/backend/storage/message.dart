// TODO: Migrate messages to object box
// 1. Create a new class Message (include memories Id maybe as oneToMany relationship)
// 2. Create messages provider
// 3. Consume stuff from messages provider
// 4. Make sure message creation includes memories properly in msg object

// class Message {
//   String id;
//   DateTime? createdAt;
//   String text;
//   String type;
//   List<String>? memoryIds; // Optional list of strings.
//   bool daySummary = false;
//
//   Message({
//     required this.text,
//     required this.type,
//     required this.id,
//     this.createdAt,
//     this.memoryIds,
//     this.daySummary = false,
//   });
//
//   // Factory constructor to create a new Message instance from a map
//   factory Message.fromJson(Map<String, dynamic> json) {
//     return Message(
//       text: json['text'] as String,
//       type: json['type'] as String,
//       id: json['id'] as String,
//       createdAt: null,
//       daySummary: json['day_summary'] as bool? ?? false,
//       memoryIds: json['memory_ids']?.cast<String>(), // Ensure this is a list of strings if not null
//     );
//   }
//
//   // Method to convert a Message instance into a map
//   Map<String, dynamic> toJson() {
//     return {
//       'id': id,
//       'text': text,
//       'type': type,
//       'created_at': createdAt?.toIso8601String(),
//       'memory_ids': memoryIds,
//       'day_summary': daySummary,
//     };
//   }
//
//   static List<Message> fromJsonList(List<dynamic> jsonList) {
//     return jsonList.map((e) => Message.fromJson(e)).toList();
//   }
// }
