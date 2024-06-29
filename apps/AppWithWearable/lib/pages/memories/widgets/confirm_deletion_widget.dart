import 'package:flutter/material.dart';
import 'package:friend_private/backend/api_requests/api/pinecone.dart';
import 'package:friend_private/backend/database/memory.dart';
import 'package:friend_private/backend/database/memory_provider.dart';
import 'package:friend_private/backend/mixpanel.dart';

class ConfirmDeletionWidget extends StatefulWidget {
  final Memory memory;
  final VoidCallback? onDelete;

  const ConfirmDeletionWidget({
    super.key,
    required this.memory,
    required this.onDelete,
  });

  @override
  State<ConfirmDeletionWidget> createState() => _ConfirmDeletionWidgetState();
}

class _ConfirmDeletionWidgetState extends State<ConfirmDeletionWidget> {
  @override
  void initState() {
    super.initState();
    WidgetsBinding.instance.addPostFrameCallback((_) => setState(() {}));
  }

  @override
  Widget build(BuildContext context) {
    return Container(
      height: 130,
      margin: const EdgeInsets.symmetric(horizontal: 16),
      decoration: BoxDecoration(
        color: Theme.of(context).colorScheme.primary,
        borderRadius: BorderRadius.circular(20),
        shape: BoxShape.rectangle,
        border: Border.all(color: Colors.grey, width: 1),
      ),
      child: Column(
        mainAxisSize: MainAxisSize.max,
        mainAxisAlignment: MainAxisAlignment.center,
        crossAxisAlignment: CrossAxisAlignment.center,
        children: [
          const SizedBox(height: 8),
          const Text(
            'Are you sure you want to delete this memory?',
            textAlign: TextAlign.center,
          ),
          const SizedBox(height: 16),
          Row(
            mainAxisSize: MainAxisSize.max,
            mainAxisAlignment: MainAxisAlignment.center,
            children: [
              Padding(
                padding: const EdgeInsetsDirectional.fromSTEB(0.0, 0.0, 12.0, 0.0),
                child: MaterialButton(
                  onPressed: () async {
                    Navigator.pop(context);
                  },
                  height: 40.0,
                  padding: const EdgeInsetsDirectional.fromSTEB(20.0, 0.0, 20.0, 0.0),
                  color: Theme.of(context).colorScheme.surface,
                  textColor: Theme.of(context).primaryColor,
                  elevation: 0.0,
                  shape: RoundedRectangleBorder(borderRadius: BorderRadius.circular(40)),
                  child: const Text(
                    'Cancel',
                    style: TextStyle(color: Colors.grey),
                  ),
                ),
              ),
              Padding(
                padding: const EdgeInsetsDirectional.fromSTEB(0.0, 0.0, 12.0, 0.0),
                child: MaterialButton(
                  onPressed: () async {
                    deleteVector(widget.memory.id.toString());
                    await MemoryProvider().deleteMemory(widget.memory);
                    Navigator.pop(context);
                    widget.onDelete?.call();
                    MixpanelManager().memoryDeleted(widget.memory);
                  },
                  height: 40.0,
                  padding: const EdgeInsetsDirectional.fromSTEB(20.0, 0.0, 20.0, 0.0),
                  color: const Color(0xFF780000),
                  textColor: Colors.white,
                  // STYLE ME
                  elevation: 0.0,
                  shape: RoundedRectangleBorder(borderRadius: BorderRadius.circular(40)),
                  child: const Text('Delete'),
                ),
              ),
            ],
          ),
        ],
      ),
    );
  }
}
