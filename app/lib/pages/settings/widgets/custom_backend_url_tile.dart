import 'package:flutter/material.dart';
import 'package:font_awesome_flutter/font_awesome_flutter.dart';

import 'package:omi/backend/preferences.dart';
import 'package:omi/env/env.dart';
import 'package:omi/pages/settings/custom_backend_url_dialog.dart';

class CustomBackendUrlTile extends StatefulWidget {
  const CustomBackendUrlTile({super.key});

  @override
  State<CustomBackendUrlTile> createState() => _CustomBackendUrlTileState();
}

class _CustomBackendUrlTileState extends State<CustomBackendUrlTile> {
  @override
  Widget build(BuildContext context) {
    final customUrl = SharedPreferencesUtil().customBackendUrl;
    final isCustom = customUrl.isNotEmpty;

    return GestureDetector(
      onTap: () async {
        final updated = await CustomBackendUrlDialog.show(context);
        if (updated == true && mounted) {
          setState(() {});
        }
      },
      child: Container(
        padding: const EdgeInsets.all(16),
        decoration: BoxDecoration(
          color: const Color(0xFF1C1C1E),
          borderRadius: BorderRadius.circular(14),
        ),
        child: Row(
          children: [
            Container(
              width: 40,
              height: 40,
              decoration: BoxDecoration(
                color: const Color(0xFF2A2A2E),
                borderRadius: BorderRadius.circular(10),
              ),
              child: Center(
                child: FaIcon(FontAwesomeIcons.server, color: Colors.grey.shade400, size: 16),
              ),
            ),
            const SizedBox(width: 14),
            Expanded(
              child: Column(
                crossAxisAlignment: CrossAxisAlignment.start,
                children: [
                  const Text(
                    'Custom Backend URL',
                    style: TextStyle(
                      color: Colors.white,
                      fontSize: 16,
                      fontWeight: FontWeight.w500,
                    ),
                  ),
                  const SizedBox(height: 2),
                  Text(
                    isCustom ? customUrl : 'Default (${Env.defaultApiBaseUrl})',
                    style: TextStyle(
                      color: isCustom ? const Color(0xFF34C759) : Colors.grey.shade500,
                      fontSize: 13,
                    ),
                    maxLines: 1,
                    overflow: TextOverflow.ellipsis,
                  ),
                ],
              ),
            ),
            if (isCustom) ...[
              Container(
                padding: const EdgeInsets.symmetric(horizontal: 8, vertical: 4),
                decoration: BoxDecoration(
                  color: Colors.grey.shade800,
                  borderRadius: BorderRadius.circular(8),
                ),
                child: const Text(
                  'Custom',
                  style: TextStyle(color: Colors.white70, fontSize: 11, fontWeight: FontWeight.w500),
                ),
              ),
              const SizedBox(width: 8),
            ],
            FaIcon(FontAwesomeIcons.chevronRight, color: Colors.grey.shade600, size: 14),
          ],
        ),
      ),
    );
  }
}
