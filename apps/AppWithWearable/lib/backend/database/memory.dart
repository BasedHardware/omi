import 'package:objectbox/objectbox.dart';

@Entity()
class Memory {
  @Id()
  int id;

  Memory({this.id = 0});
}
