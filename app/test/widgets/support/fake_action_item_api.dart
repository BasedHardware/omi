import 'package:omi/backend/schema/schema.dart';

/// A stand-in for `api.updateActionItem` that confirms the write without a
/// network call.
///
/// [ActionItemsProvider.updateActionItemState] applies its change optimistically
/// and rolls it back when the request returns null. Against the real API a
/// widget test has no auth, so every toggle would roll back and the assertions
/// would be testing the failure path by accident. Returning a non-null item is
/// what makes the completion stick.
Future<ActionItemWithMetadata?> fakeUpdate(
  String actionItemId, {
  String? description,
  bool? completed,
  DateTime? dueAt,
}) async {
  final now = DateTime(2026, 8, 7, 9);
  return ActionItemWithMetadata(
    id: actionItemId,
    description: description ?? '',
    completed: completed ?? false,
    createdAt: now,
    updatedAt: now,
    completedAt: (completed ?? false) ? now : null,
    dueAt: dueAt,
    sortOrder: 0,
    source: 'test',
    status: 'active',
  );
}
