import 'package:flutter/material.dart';

class ToggleSectionWidget extends StatefulWidget {
  final bool isSectionEnabled;
  final String sectionTitle;
  final String sectionDescription;
  final List<Widget> options;
  final Function(bool) onSectionEnabledChanged;
  final IconData? icon;

  const ToggleSectionWidget({
    super.key,
    required this.isSectionEnabled,
    required this.sectionTitle,
    required this.sectionDescription,
    required this.options,
    required this.onSectionEnabledChanged,
    this.icon,
  });

  @override
  State<ToggleSectionWidget> createState() => _ToggleSectionWidgetState();
}

class _ToggleSectionWidgetState extends State<ToggleSectionWidget> {
  @override
  Widget build(BuildContext context) {
    return Column(
      mainAxisSize: MainAxisSize.min,
      children: [
        ListTile(
          dense: false,
          contentPadding: const EdgeInsets.symmetric(horizontal: 10, vertical: 4),
          minVerticalPadding: 0,
          leading: widget.icon != null
              ? Container(
                  padding: const EdgeInsets.all(8),
                  decoration: BoxDecoration(
                    color: const Color.fromARGB(255, 28, 28, 28),
                    borderRadius: BorderRadius.circular(8),
                  ),
                  child: Icon(
                    widget.icon,
                    color: Colors.white,
                    size: 22,
                  ),
                )
              : null,
          title: Text(
            widget.sectionTitle,
            style: const TextStyle(
              color: Colors.white,
              fontSize: 16,
              fontWeight: FontWeight.w600,
            ),
          ),
          subtitle: Text(
            widget.sectionDescription,
            style: TextStyle(
              color: Colors.white.withOpacity(0.5),
              fontSize: 13,
            ),
          ),
          trailing: Switch(
            value: widget.isSectionEnabled,
            onChanged: widget.onSectionEnabledChanged,
          ),
        ),
        AnimatedCrossFade(
          firstChild: const SizedBox.shrink(),
          secondChild: Padding(
            padding: const EdgeInsets.fromLTRB(16, 8, 16, 8),
            child: Column(
              mainAxisSize: MainAxisSize.min,
              crossAxisAlignment: CrossAxisAlignment.start,
              mainAxisAlignment: MainAxisAlignment.start,
              children: widget.options,
            ),
          ),
          crossFadeState: widget.isSectionEnabled ? CrossFadeState.showSecond : CrossFadeState.showFirst,
          duration: const Duration(milliseconds: 300),
          sizeCurve: Curves.easeInOut,
        ),
      ],
    );
  }
}
