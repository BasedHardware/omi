import 'package:flutter/material.dart';

import 'package:provider/provider.dart';

import 'package:omi/backend/schema/review.dart';
import 'package:omi/pages/conversation_detail/widgets/conversation_detail_chip.dart';
import 'package:omi/pages/entities/entity_page.dart';
import 'package:omi/pages/review/widgets/review_parts.dart';
import 'package:omi/providers/review_provider.dart';
import 'package:omi/ui/ui.dart';

/// The organizations and projects a conversation belongs to, as chips under its title. Each opens
/// that entity's page. Nothing is drawn (and nothing fetched) while Review is off for the account.
class ConversationEntityChips extends StatefulWidget {
  const ConversationEntityChips({super.key, required this.conversationId});

  final String conversationId;

  @override
  State<ConversationEntityChips> createState() => _ConversationEntityChipsState();
}

class _ConversationEntityChipsState extends State<ConversationEntityChips> {
  List<EntityRef> _entities = const [];
  String? _loadedFor;

  @override
  void didChangeDependencies() {
    super.didChangeDependencies();
    _maybeLoad();
  }

  @override
  void didUpdateWidget(covariant ConversationEntityChips oldWidget) {
    super.didUpdateWidget(oldWidget);
    if (oldWidget.conversationId != widget.conversationId) {
      _entities = const [];
      _maybeLoad(listen: false);
    }
  }

  Future<void> _maybeLoad({bool listen = true}) async {
    // Listening from didChangeDependencies re-runs it when Review turns on after the page opened.
    final review = Provider.of<ReviewProvider?>(context, listen: listen);
    final id = widget.conversationId;
    if (review == null || !review.isOn || _loadedFor == id) return;
    _loadedFor = id;
    final entities = await review.conversationEntities(id);
    if (!mounted || widget.conversationId != id) return;
    setState(() {
      _entities = [
        ...entities.where((e) => e.type == EntityType.organization),
        ...entities.where((e) => e.type == EntityType.project),
      ].take(4).toList(growable: false);
    });
  }

  @override
  Widget build(BuildContext context) {
    if (_entities.isEmpty) return const SizedBox.shrink();
    return Padding(
      padding: const EdgeInsets.only(top: 8),
      child: Wrap(
        spacing: 8,
        runSpacing: 8,
        children: [
          for (final entity in _entities)
            Semantics(
              button: true,
              label: entity.name,
              excludeSemantics: true,
              child: GestureDetector(
                key: ValueKey('conversation_entity_${entity.entityId}'),
                onTap: () => openEntityPage(context, entity),
                child: ConversationDetailChip(
                  icon: Icon(entityIcon(entity.type), size: 15, color: OmiColors.textPrimary),
                  label: entity.name,
                ),
              ),
            ),
        ],
      ),
    );
  }
}
