import 'package:flutter/material.dart';
import 'package:friend_private/backend/schema/memory.dart';
import 'package:friend_private/pages/memories/widgets/processing_memory_capture.dart';
import 'package:friend_private/utils/other/temp.dart';
import 'package:gradient_borders/box_borders/gradient_box_border.dart';

class ProcessingMemoryWidget extends StatefulWidget {
  final ServerProcessingMemory memory;

  const ProcessingMemoryWidget({
    super.key,
    required this.memory,
  });

  @override
  State<ProcessingMemoryWidget> createState() => _ProcessingMemoryWidgetState();
}

class _ProcessingMemoryWidgetState extends State<ProcessingMemoryWidget> {
  @override
  Widget build(BuildContext context) {
    return GestureDetector(
      child: Container(
        margin: const EdgeInsets.only(top: 12, left: 8, right: 8),
        width: double.maxFinite,
        decoration: const BoxDecoration(
          color: Colors.black,
          borderRadius: BorderRadius.all(Radius.circular(16)),
          border: GradientBoxBorder(
            gradient: LinearGradient(colors: [
              Color.fromARGB(127, 208, 208, 208),
              Color.fromARGB(127, 188, 99, 121),
              Color.fromARGB(127, 86, 101, 182),
              Color.fromARGB(127, 126, 190, 236)
            ]),
            width: 1,
          ),
          shape: BoxShape.rectangle,
        ),
        child: Padding(
          padding: const EdgeInsetsDirectional.all(16),
          child: Column(
            mainAxisSize: MainAxisSize.max,
            crossAxisAlignment: CrossAxisAlignment.start,
            children: [
              _getMemoryHeader(),
              const SizedBox(height: 16),
              const Expanded(
                child: CustomScrollView(
                  slivers: [
                    SliverToBoxAdapter(child: SizedBox(height: 32)),
                    SliverToBoxAdapter(
                      child: CaptureWidget(),
                    ),
                  ],
                ),
              ),
            ],
          ),
        ),
      ),
    );
  }

  _getMemoryHeader() {
    return Padding(
      padding: const EdgeInsets.only(left: 4.0, right: 12),
      child: Row(
        mainAxisAlignment: MainAxisAlignment.spaceBetween,
        children: [
          Container(
            decoration: const BoxDecoration(
              color: Colors.black,
              borderRadius: BorderRadius.all(Radius.circular(16)),
              border: GradientBoxBorder(
                gradient: LinearGradient(colors: [
                  Color.fromARGB(127, 208, 208, 208),
                  Color.fromARGB(127, 188, 99, 121),
                  Color.fromARGB(127, 86, 101, 182),
                  Color.fromARGB(127, 126, 190, 236)
                ]),
                width: 1,
              ),
              shape: BoxShape.rectangle,
            ),
            padding: const EdgeInsets.symmetric(horizontal: 12, vertical: 6),
            child: Row(
              children: [
                Image.asset(
                  "assets/images/recording_green_circle_icon.png",
                  width: 10,
                  height: 10,
                ),
                const SizedBox(
                  width: 4,
                ),
                Text(
                  "Friend (A7AF24)", // TODO:
                  style: Theme.of(context).textTheme.bodyMedium!.copyWith(color: Colors.white),
                  maxLines: 1,
                ),
              ],
            ),
          ),
          const SizedBox(
            width: 16,
          ),
          Expanded(
            child: Text(
              "Recording • ${dateTimeFormat('h:mm a', widget.memory.startedAt ?? widget.memory.createdAt)}",
              style: TextStyle(color: Colors.grey.shade400, fontSize: 14),
              maxLines: 1,
              textAlign: TextAlign.end,
            ),
          )
        ],
      ),
    );
  }
}

Widget getProcessingMemoryWidget(ServerProcessingMemory memory) {
  return ProcessingMemoryWidget(memory: memory);
}
