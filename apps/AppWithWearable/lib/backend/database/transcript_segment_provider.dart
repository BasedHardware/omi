import 'package:friend_private/backend/database/box.dart';
import 'package:friend_private/backend/database/transcript_segment.dart';
import 'package:friend_private/objectbox.g.dart';

class TranscriptSegmentProvider {
  static final TranscriptSegmentProvider _instance = TranscriptSegmentProvider._internal();
  static final Box<TranscriptSegment> _box = ObjectBoxUtil().box!.store.box<TranscriptSegment>();

  factory TranscriptSegmentProvider() {
    return _instance;
  }

  TranscriptSegmentProvider._internal();
}
