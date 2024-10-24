import 'package:flutter/material.dart';

class ToggleSectionWidget extends StatefulWidget {
  final bool isSectionEnabled;
  final String sectionTitle;
  final String sectionDescription;
  final List<Widget> options;
  final Function(bool) onSectionEnabledChanged;

  const ToggleSectionWidget(
      {super.key,
      required this.isSectionEnabled,
      required this.sectionTitle,
      required this.sectionDescription,
      required this.options,
      required this.onSectionEnabledChanged});
  @override
  State<ToggleSectionWidget> createState() => _ToggleSectionWidgetState();
}

class _ToggleSectionWidgetState extends State<ToggleSectionWidget> {
  @override
  void initState() {
    super.initState();
  }

  @override
  void dispose() {
    super.dispose();
  }

  @override
  Widget build(BuildContext context) {
    return ListView(
      shrinkWrap: true,
      physics: const NeverScrollableScrollPhysics(),
      children: [
        ListTile(
          title: Text(
            widget.sectionTitle,
            style: TextStyle(color: Colors.white, fontSize: 16, fontWeight: FontWeight.w600),
          ),
          contentPadding: EdgeInsets.zero,
          subtitle: Text(widget.sectionDescription),
          trailing: Switch(
            value: widget.isSectionEnabled,
            onChanged: widget.onSectionEnabledChanged,
          ),
        ),
        AnimatedCrossFade(
          firstChild: const SizedBox.shrink(),
          secondChild: Column(
            mainAxisSize: MainAxisSize.min,
            crossAxisAlignment: CrossAxisAlignment.start,
            mainAxisAlignment: MainAxisAlignment.start,
            children: widget.options,
          ),
          crossFadeState: widget.isSectionEnabled ? CrossFadeState.showSecond : CrossFadeState.showFirst,
          duration: const Duration(milliseconds: 300),
        ),
      ],
    );
  }
}
