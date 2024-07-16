import 'package:auto_size_text/auto_size_text.dart';
import 'package:flutter/material.dart';
import 'package:flutter/services.dart';
import 'package:friend_private/backend/database/memory.dart';
import 'package:friend_private/backend/database/message.dart';
import 'package:friend_private/backend/mixpanel.dart';
import 'package:friend_private/backend/schema/plugin.dart';
import 'package:friend_private/pages/memory_detail/page.dart';
import 'package:friend_private/utils/other/temp.dart';

class AIMessage extends StatelessWidget {
  final Message message;
  final Function(String) sendMessage;
  final bool displayOptions;
  final List<Memory> memories;
  final Plugin? pluginSender;

  const AIMessage({
    super.key,
    required this.message,
    required this.sendMessage,
    required this.displayOptions,
    required this.memories,
    this.pluginSender,
  });

  @override
  Widget build(BuildContext context) {
    return Row(
      mainAxisSize: MainAxisSize.max,
      crossAxisAlignment: CrossAxisAlignment.start,
      children: [
        pluginSender != null
            ? CircleAvatar(
                radius: 16,
                backgroundImage: NetworkImage(pluginSender!.getImageUrl()),
              )
            : Container(
                decoration: const BoxDecoration(
                  image: DecorationImage(
                    image: AssetImage("assets/images/background.png"),
                    fit: BoxFit.cover,
                  ),
                  borderRadius: BorderRadius.all(Radius.circular(16.0)),
                ),
                height: 32,
                width: 32,
                child: Stack(
                  alignment: Alignment.center,
                  children: [
                    Image.asset(
                      "assets/images/herologo.png",
                      height: 24,
                      width: 24,
                    ),
                  ],
                ),
              ),
        const SizedBox(width: 16.0),
        Expanded(
          child: Column(
            mainAxisSize: MainAxisSize.max,
            crossAxisAlignment: CrossAxisAlignment.start,
            children: [
              const SizedBox(height: 6),
              message.typeEnum == MessageType.daySummary
                  ? Text(
                      '📅  Day Summary ~ ${dateTimeFormat('MMM, dd', DateTime.now())}',
                      style: TextStyle(
                        fontSize: 18,
                        fontWeight: FontWeight.w500,
                        color: Colors.grey.shade300,
                        decoration: TextDecoration.underline,
                      ),
                    )
                  : const SizedBox(),
              message.typeEnum == MessageType.daySummary ? const SizedBox(height: 16) : const SizedBox(),
              SelectionArea(
                  child: AutoSizeText(
                message.text.isEmpty ? '...' : message.text.replaceAll(r'\n', '\n').replaceAll('**', '').replaceAll('\\"', '\"'),
                style: TextStyle(fontSize: 15.0, fontWeight: FontWeight.w500, color: Colors.grey.shade300),
              )),
              if (message.id != 1) _getCopyButton(context),
              if (message.id == 1 && displayOptions) const SizedBox(height: 8),
              if (message.id == 1 && displayOptions) ..._getInitialOptions(context),
              if (memories.isNotEmpty) ...[
                const SizedBox(height: 16),
                for (var memory in (memories.length > 3 ? memories.sublist(0, 3) : memories)) ...[
                  Padding(
                    padding: const EdgeInsetsDirectional.fromSTEB(0.0, 0.0, 0.0, 4.0),
                    child: GestureDetector(
                      onTap: () async {
                        MixpanelManager().chatMessageMemoryClicked(memory);
                        await Navigator.of(context)
                            .push(MaterialPageRoute(builder: (c) => MemoryDetailPage(memory: memory)));
                        // TODO: maybe refresh memories here too
                      },
                      child: Container(
                        padding: const EdgeInsets.symmetric(horizontal: 12.0, vertical: 8),
                        width: double.maxFinite,
                        decoration: BoxDecoration(
                          color: Colors.grey.shade900,
                          borderRadius: BorderRadius.circular(12.0),
                        ),
                        child: Row(
                          children: [
                            Expanded(
                              child: Text(
                                memory.structured.target!.title,
                                style: Theme.of(context).textTheme.bodyMedium,
                                maxLines: 1,
                                overflow: TextOverflow.ellipsis,
                              ),
                            ),
                            const SizedBox(width: 8),
                            const Icon(Icons.arrow_right_alt)
                          ],
                        ),
                      ),
                    ),
                  ),
                ],
              ],
            ],
          ),
        ),
      ],
    );
  }

  _getCopyButton(BuildContext context) {
    return Padding(
      padding: const EdgeInsetsDirectional.fromSTEB(0.0, 6.0, 0.0, 0.0),
      child: InkWell(
        splashColor: Colors.transparent,
        focusColor: Colors.transparent,
        hoverColor: Colors.transparent,
        highlightColor: Colors.transparent,
        onTap: () async {
          await Clipboard.setData(ClipboardData(text: message.text));
          ScaffoldMessenger.of(context).showSnackBar(
            const SnackBar(
              content: Text(
                'Response copied to clipboard.',
                style: TextStyle(
                  color: Color.fromARGB(255, 255, 255, 255),
                  fontSize: 12.0,
                ),
              ),
              duration: Duration(milliseconds: 2000),
            ),
          );
        },
        child: Row(
          mainAxisSize: MainAxisSize.max,
          children: [
            Padding(
              padding: const EdgeInsetsDirectional.fromSTEB(0.0, 0.0, 4.0, 0.0),
              child: Icon(
                Icons.content_copy,
                color: Theme.of(context).textTheme.bodySmall!.color,
                size: 10.0,
              ),
            ),
            Text(
              'Copy response',
              style: Theme.of(context).textTheme.bodySmall,
            ),
          ],
        ),
      ),
    );
  }

  _getInitialOption(BuildContext context, String optionText) {
    return GestureDetector(
      child: Container(
        padding: const EdgeInsets.symmetric(horizontal: 12.0, vertical: 8),
        width: double.maxFinite,
        decoration: BoxDecoration(
          color: Colors.grey.shade900,
          borderRadius: BorderRadius.circular(12.0),
        ),
        child: Text(optionText, style: Theme.of(context).textTheme.bodyMedium),
      ),
      onTap: () {
        sendMessage(optionText);
      },
    );
  }

  _getInitialOptions(BuildContext context) {
    return [
      const SizedBox(height: 8),
      _getInitialOption(context, 'What tasks do I have from yesterday?'),
      const SizedBox(height: 8),
      _getInitialOption(context, 'What conversations did I have with John?'),
      const SizedBox(height: 8),
      _getInitialOption(context, 'What advise have I received about entrepreneurship?'),
    ];
  }
}
