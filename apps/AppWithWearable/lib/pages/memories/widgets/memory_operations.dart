import 'package:flutter/material.dart';
import 'package:flutter/services.dart';
import 'package:font_awesome_flutter/font_awesome_flutter.dart';
import 'package:friend_private/backend/storage/memories.dart';
import 'package:friend_private/flutter_flow/flutter_flow_theme.dart';
import 'package:friend_private/flutter_flow/flutter_flow_util.dart';
import 'package:friend_private/pages/memories/widgets/confirm_deletion_widget.dart';
import 'package:friend_private/pages/memories/widgets/edit_memory_widget.dart';
import 'package:share_plus/share_plus.dart';

getMemoryOperations(MemoryRecord memory, FocusNode unFocusNode, StateSetter setState) {
  return Container(
    padding: const EdgeInsetsDirectional.symmetric(horizontal: 12, vertical: 8),
    decoration: BoxDecoration(
      color: const Color(0xFF515253),
      borderRadius: BorderRadius.circular(24.0),
    ),
    child: Row(
      mainAxisSize: MainAxisSize.min,
      mainAxisAlignment: MainAxisAlignment.center,
      children: [
        geyShareMemoryOperationWidget(memory),
        const SizedBox(width: 10.0),
        getEditMemoryOperationWidget(memory, unFocusNode, setState),
        const SizedBox(width: 10.0),
        getDeleteMemoryOperationWidget(memory, unFocusNode, setState),
      ],
    ),
  );
}

geyShareMemoryOperationWidget(MemoryRecord memory, {double iconSize = 20}) {
  return Builder(
    builder: (context) => InkWell(
      splashColor: Colors.transparent,
      focusColor: Colors.transparent,
      hoverColor: Colors.transparent,
      highlightColor: Colors.transparent,
      onTap: () async {
        await Share.share(
          '${memory.structuredMemory}  Created with https://www.aisama.co/',
          sharePositionOrigin: getWidgetBoundingBox(context),
        );
        HapticFeedback.lightImpact();
      },
      child: FaIcon(
        FontAwesomeIcons.share,
        color: FlutterFlowTheme.of(context).secondaryText,
        size: iconSize,
      ),
    ),
  );
}

getEditMemoryOperationWidget(MemoryRecord memory, FocusNode unFocusNode, StateSetter setState, {double iconSize = 20}) {
  return Builder(
    builder: (context) => InkWell(
      splashColor: Colors.transparent,
      focusColor: Colors.transparent,
      hoverColor: Colors.transparent,
      highlightColor: Colors.transparent,
      onTap: () async {
        await showDialog(
          context: context,
          builder: (dialogContext) {
            return Dialog(
              elevation: 0,
              insetPadding: EdgeInsets.zero,
              backgroundColor: Colors.transparent,
              alignment: const AlignmentDirectional(0.0, 0.0).resolve(Directionality.of(context)),
              child: GestureDetector(
                onTap: () => unFocusNode.canRequestFocus
                    ? FocusScope.of(context).requestFocus(unFocusNode)
                    : FocusScope.of(context).unfocus(),
                child: EditMemoryWidget(memory: memory),
              ),
            );
          },
        ).then((value) => setState(() {}));
      },
      child: Icon(
        Icons.edit,
        color: FlutterFlowTheme.of(context).secondaryText,
        size: iconSize,
      ),
    ),
  );
}

getDeleteMemoryOperationWidget(MemoryRecord memory, FocusNode unFocusNode, StateSetter setState,
    {double iconSize = 20, VoidCallback? onDelete}) {
  return Builder(
    builder: (context) => InkWell(
      splashColor: Colors.transparent,
      focusColor: Colors.transparent,
      hoverColor: Colors.transparent,
      highlightColor: Colors.transparent,
      onTap: () async {
        await showDialog(
          context: context,
          builder: (dialogContext) {
            return Dialog(
              elevation: 0,
              insetPadding: EdgeInsets.zero,
              backgroundColor: Colors.transparent,
              alignment: const AlignmentDirectional(0.0, 0.0).resolve(Directionality.of(context)),
              child: GestureDetector(
                onTap: () => unFocusNode.canRequestFocus
                    ? FocusScope.of(context).requestFocus(unFocusNode)
                    : FocusScope.of(context).unfocus(),
                child: ConfirmDeletionWidget(memory: memory, onDelete: onDelete),
              ),
            );
          },
        ).then((value) => setState(() {}));
      },
      child: Icon(
        Icons.delete,
        color: FlutterFlowTheme.of(context).secondaryText,
        size: iconSize,
      ),
    ),
  );
}
