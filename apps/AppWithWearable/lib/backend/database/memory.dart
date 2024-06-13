import 'package:objectbox/objectbox.dart';

@Entity()
class Memory {
  @Id()
  int id = 0;

  @Index()
  @Property(type: PropertyType.date)
  DateTime createdAt;

  String transcript;
  String? recordingFilePath;
  final structured = ToOne<Structured>();

  @Backlink('memory')
  final pluginsResponse = ToMany<PluginResponse>();

  @Index()
  bool discarded;

  Memory(this.createdAt, this.transcript, this.discarded, {this.id = 0});
}

@Entity()
class Structured {
  @Id()
  int id = 0;

  String title;
  String overview;
  String emoji;
  String category;

  @Backlink('structured')
  final actionItems = ToMany<ActionItem>();

  Structured(this.title, this.overview, {this.emoji = '', this.category = 'other'});
}

@Entity()
class ActionItem {
  @Id()
  int id = 0;

  String description;
  bool completed = false;
  final structured = ToOne<Structured>();

  ActionItem(this.description, {this.id = 0, this.completed = false});
}

@Entity()
class PluginResponse {
  @Id()
  int id = 0;

  String response;
  final memory = ToOne<Memory>();

  PluginResponse(this.response);
}
