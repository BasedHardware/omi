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

getItemAddOn2(String title, VoidCallback onTap, {required IconData icon}) {
  return GestureDetector(
    onTap: () {
      MixpanelManager().pageOpened('Settings $title');
      onTap();
    },
    child: Padding(
      padding: const EdgeInsets.fromLTRB(0, 0, 0, 0),
      child: Container(
        decoration: BoxDecoration(
          color: const Color.fromARGB(255, 29, 29, 29),
          borderRadius: BorderRadius.circular(10.0),
        ),
        child: Padding(
          padding: const EdgeInsets.symmetric(horizontal: 16, vertical: 16),
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
                  Icon(icon, color: Colors.white, size: 18),
                ],
              ),
              const Icon(Icons.arrow_forward_ios, color: Colors.white, size: 16),
            ],
          ),
        ),
      ),
    ),
  );
}
