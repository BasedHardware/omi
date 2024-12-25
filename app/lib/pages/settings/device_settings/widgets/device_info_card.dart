import 'package:flutter/material.dart';
import 'package:friend_private/backend/schema/bt_device/bt_device.dart';

class DeviceInfoCard extends StatelessWidget {
  final BtDevice? device;
  const DeviceInfoCard({super.key, this.device});

  @override
  Widget build(BuildContext context) {
    return Container(
      decoration: BoxDecoration(
        color: const Color.fromARGB(255, 18, 18, 18),
        borderRadius: BorderRadius.circular(12.0),
        border: Border.all(
          color: Colors.white.withOpacity(0.15),
          width: 1,
        ),
      ),
      padding: const EdgeInsets.all(16),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          Row(
            children: [
              Container(
                padding: const EdgeInsets.all(8),
                decoration: BoxDecoration(
                  color: const Color.fromARGB(255, 28, 28, 28),
                  borderRadius: BorderRadius.circular(8),
                ),
                child: const Icon(
                  Icons.devices,
                  color: Colors.white,
                  size: 22,
                ),
              ),
              const SizedBox(width: 16),
              Text(
                device?.name ?? 'Friend',
                style: const TextStyle(
                  color: Colors.white,
                  fontSize: 18,
                  fontWeight: FontWeight.w500,
                ),
              ),
            ],
          ),
          const SizedBox(height: 16),
          DeviceInfoRow(label: 'Device ID', value: device?.id ?? '12AB34CD:56EF78GH'),
          const SizedBox(height: 8),
          DeviceInfoRow(label: 'Hardware', value: device?.hardwareRevision ?? 'XIAO'),
          const SizedBox(height: 8),
          DeviceInfoRow(label: 'Model', value: device?.modelNumber ?? 'Friend'),
          const SizedBox(height: 8),
          DeviceInfoRow(label: 'Manufacturer', value: device?.manufacturerName ?? 'Based Hardware'),
        ],
      ),
    );
  }
}

class DeviceInfoRow extends StatelessWidget {
  final String label;
  final String value;
  const DeviceInfoRow({super.key, required this.label, required this.value});

  @override
  Widget build(BuildContext context) {
    return Row(
      crossAxisAlignment: CrossAxisAlignment.start,
      children: [
        SizedBox(
          width: MediaQuery.sizeOf(context).width * 0.24,
          child: Text(
            label,
            style: TextStyle(
              color: Colors.white.withOpacity(0.5),
              fontSize: 14,
            ),
          ),
        ),
        Expanded(
          child: Text(
            value,
            style: const TextStyle(
              color: Colors.white,
              fontSize: 14,
            ),
          ),
        ),
      ],
    );
  }
}
