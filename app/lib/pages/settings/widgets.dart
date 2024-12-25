import 'package:flutter/material.dart';
import 'package:friend_private/utils/analytics/mixpanel.dart';

getItemAddonWrapper(List<Widget> widgets) {
  return Card(
    shape: const RoundedRectangleBorder(borderRadius: BorderRadius.all(Radius.circular(8))),
    child: Column(
      children: widgets,
    ),
  );
}

getItemAddOn(String title, VoidCallback onTap, {required IconData icon, bool visibility = true}) {
  return Visibility(
    visible: visibility,
    child: GestureDetector(
      onTap: onTap,
      child: Padding(
        padding: const EdgeInsets.fromLTRB(0, 12, 8, 0),
        child: Container(
          decoration: BoxDecoration(
            color: const Color.fromARGB(255, 29, 29, 29), // Replace with your desired color
            borderRadius: BorderRadius.circular(10.0), // Adjust for desired rounded corners
          ),
          child: Padding(
            padding: const EdgeInsets.symmetric(horizontal: 16, vertical: 12),
            child: Row(
              mainAxisAlignment: MainAxisAlignment.spaceBetween,
              children: [
                Row(
                  children: [
                    Text(
                      title,
                      style: const TextStyle(color: Color.fromARGB(255, 150, 150, 150), fontSize: 16),
                    ),
                    const SizedBox(width: 16),
                    Icon(icon, color: Colors.white, size: 16),
                  ],
                ),
                const Icon(Icons.arrow_forward_ios, color: Colors.white, size: 16),
              ],
            ),
          ),
        ),
      ),
    ),
  );
}

class CustomListTile extends StatelessWidget {
  final String title;
  final VoidCallback onTap;
  final IconData icon;
  final String? subtitle;
  final IconData? trailingIcon;
  final bool showChevron;

  const CustomListTile(
      {super.key,
      required this.title,
      required this.onTap,
      required this.icon,
      this.subtitle,
      this.trailingIcon,
      required this.showChevron});

  @override
  Widget build(BuildContext context) {
    return GestureDetector(
      onTap: () {
        MixpanelManager().pageOpened('Settings $title');
        onTap();
      },
      child: Container(
        decoration: BoxDecoration(
          color: const Color.fromARGB(255, 18, 18, 18),
          borderRadius: BorderRadius.circular(12.0),
          border: Border.all(
            color: Colors.white.withOpacity(0.15),
            width: 1,
          ),
        ),
        child: Padding(
          padding: const EdgeInsets.symmetric(horizontal: 16, vertical: 12),
          child: Row(
            children: [
              Container(
                padding: const EdgeInsets.all(8),
                decoration: BoxDecoration(
                  color: const Color.fromARGB(255, 28, 28, 28),
                  borderRadius: BorderRadius.circular(8),
                ),
                child: Icon(
                  icon,
                  color: Colors.white,
                  size: 22,
                ),
              ),
              const SizedBox(width: 16),
              Expanded(
                child: Column(
                  crossAxisAlignment: CrossAxisAlignment.start,
                  children: [
                    Text(
                      title,
                      style: const TextStyle(
                        color: Colors.white,
                        fontSize: 16,
                        fontWeight: FontWeight.w400,
                      ),
                    ),
                    if (subtitle != null) ...[
                      const SizedBox(height: 4),
                      Text(
                        subtitle!,
                        style: TextStyle(
                          color: Colors.white.withOpacity(0.5),
                          fontSize: 14,
                          fontWeight: FontWeight.w400,
                        ),
                      ),
                    ],
                  ],
                ),
              ),
              if (trailingIcon != null)
                Icon(
                  trailingIcon,
                  color: Colors.white.withOpacity(0.5),
                  size: 20,
                )
              else if (showChevron)
                Icon(
                  Icons.chevron_right_rounded,
                  color: Colors.white.withOpacity(0.5),
                  size: 20,
                ),
            ],
          ),
        ),
      ),
    );
  }
}
