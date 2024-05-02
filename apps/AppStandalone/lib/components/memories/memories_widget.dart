import 'package:sama/backend/storage/memories.dart';
import 'package:sama/components/memories/memory_list_item.dart';

import '/components/empty_memories_widget.dart';
import '/flutter_flow/flutter_flow_theme.dart';
import 'package:flutter/material.dart';

// TODO: not being used anywhere, should remove?
class MemoriesWidget extends StatefulWidget {
  const MemoriesWidget({super.key});

  @override
  State<MemoriesWidget> createState() => _MemoriesWidgetState();
}

class _MemoriesWidgetState extends State<MemoriesWidget> {
  late Future<List<MemoryRecord>> _memoryList;

  Future<void> _refreshMemories() async {
    setState(() {
      _memoryList = MemoryStorage.getAllMemories();
    });
  }

  @override
  void initState() {
    super.initState();
    WidgetsBinding.instance.addPostFrameCallback((_) => setState(() {}));
    _memoryList = MemoryStorage.getAllMemories();
  }

  @override
  Widget build(BuildContext context) {
    debugPrint('memories_widget.dart log');
    return FutureBuilder<List<MemoryRecord>>(
      future: _memoryList,
      builder: (context, snapshot) {
        if (!snapshot.hasData || snapshot.connectionState == ConnectionState.waiting) {
          return Center(
            child: SizedBox(
              width: 50.0,
              height: 50.0,
              child: CircularProgressIndicator(
                valueColor: AlwaysStoppedAnimation<Color>(
                  FlutterFlowTheme.of(context).primary,
                ),
              ),
            ),
          );
        }
        List<MemoryRecord> memories = snapshot.data!;
        if (memories.isEmpty) {
          return Center(
            child: SizedBox(
              width: MediaQuery.sizeOf(context).width * 1.0,
              height: MediaQuery.sizeOf(context).height * 0.4,
              child: const EmptyMemoriesWidget(),
            ),
          );
        }
        return ListView.builder(
          padding: EdgeInsets.zero,
          primary: false,
          shrinkWrap: true,
          scrollDirection: Axis.vertical,
          itemCount: memories.length,
          itemBuilder: (context, listViewIndex) {
            final memory = memories[listViewIndex];
            return Container(child: Text('Hi'));
            // return MemoryListItem(
            //   memory: memory,
            //   model: null,
            // );
          },
        );
      },
    );
  }
}
