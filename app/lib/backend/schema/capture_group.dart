import 'package:omi/backend/schema/gen/conversation_wire.g.dart' as wire;

/// One device's recording inside a [CaptureGroup].
class CaptureGroupMember {
  final String id;

  /// Wire source (`desktop`, `omi`, `phone`, `apple_watch`, ...). Kept as the
  /// raw string so a source this build does not know still round-trips.
  final String? source;
  final DateTime? startedAt;
  final DateTime? finishedAt;

  const CaptureGroupMember({required this.id, this.source, this.startedAt, this.finishedAt});

  factory CaptureGroupMember.fromGenerated(wire.GeneratedCaptureGroupMember generated) {
    return CaptureGroupMember(
      id: generated.id,
      source: generated.source,
      startedAt: generated.startedAt,
      finishedAt: generated.finishedAt,
    );
  }

  wire.GeneratedCaptureGroupMember toGenerated() {
    return wire.GeneratedCaptureGroupMember(id: id, source: source, startedAt: startedAt, finishedAt: finishedAt);
  }
}

/// Conversations from different capture surfaces (desktop, pendant, phone)
/// that recorded one real-world event. Server-authored only after the
/// captures are shown to share speech, and identical on every member; [id] is
/// the event identity and survives a change of [primaryId].
class CaptureGroup {
  final String id;
  final String primaryId;
  final int revision;
  final List<CaptureGroupMember> members;

  const CaptureGroup({required this.id, required this.primaryId, this.revision = 1, this.members = const []});

  factory CaptureGroup.fromGenerated(wire.GeneratedCaptureGroup generated) {
    return CaptureGroup(
      id: generated.id,
      primaryId: generated.primaryId,
      revision: generated.revision,
      members: generated.members.map(CaptureGroupMember.fromGenerated).toList(),
    );
  }

  factory CaptureGroup.fromJson(Map<String, dynamic> json) =>
      CaptureGroup.fromGenerated(wire.GeneratedCaptureGroup.fromJson(json));

  wire.GeneratedCaptureGroup toGenerated() {
    return wire.GeneratedCaptureGroup(
      id: id,
      primaryId: primaryId,
      revision: revision,
      members: members.map((member) => member.toGenerated()).toList(),
    );
  }

  Map<String, dynamic> toJson() => toGenerated().toJson();
}
