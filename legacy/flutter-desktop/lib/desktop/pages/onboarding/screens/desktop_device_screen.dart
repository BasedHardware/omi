// import 'package:flutter/material.dart';
// import 'package:omi/backend/schema/bt_device/bt_device.dart';
// import 'package:omi/providers/onboarding_provider.dart';
// import 'package:provider/provider.dart';

// class DesktopDeviceScreen extends StatefulWidget {
//   final VoidCallback onNext;
//   final VoidCallback onBack;

//   const DesktopDeviceScreen({
//     super.key,
//     required this.onNext,
//     required this.onBack,
//   });

//   @override
//   State<DesktopDeviceScreen> createState() => _DesktopDeviceScreenState();
// }

// class _DesktopDeviceScreenState extends State<DesktopDeviceScreen> with TickerProviderStateMixin {
//   late AnimationController _scanController;
//   late Animation<double> _scanAnimation;
//   bool _isScanning = false;
//   BTDeviceStruct? _selectedDevice;

//   @override
//   void initState() {
//     super.initState();
//     _scanController = AnimationController(
//       duration: const Duration(seconds: 2),
//       vsync: this,
//     );
//     _scanAnimation = Tween<double>(
//       begin: 0.0,
//       end: 1.0,
//     ).animate(CurvedAnimation(
//       parent: _scanController,
//       curve: Curves.easeInOut,
//     ));
//   }

//   @override
//   void dispose() {
//     _scanController.dispose();
//     super.dispose();
//   }

//   void _startScanning() {
//     setState(() {
//       _isScanning = true;
//     });
//     _scanController.repeat();

//     final provider = context.read<OnboardingProvider>();
//     provider.scanDevices();

//     // Auto-stop scanning after 30 seconds
//     Future.delayed(const Duration(seconds: 30), () {
//       if (mounted && _isScanning) {
//         _stopScanning();
//       }
//     });
//   }

//   void _stopScanning() {
//     setState(() {
//       _isScanning = false;
//     });
//     _scanController.stop();
//     _scanController.reset();

//     final provider = context.read<OnboardingProvider>();
//     provider.stopScanning();
//   }

//   void _selectDevice(BTDeviceStruct device) {
//     setState(() {
//       _selectedDevice = device;
//     });

//     final provider = context.read<OnboardingProvider>();
//     provider.setSelectedDevice(device);
//   }

//   void _connectDevice() async {
//     if (_selectedDevice != null) {
//       final provider = context.read<OnboardingProvider>();
//       _stopScanning();

//       // Show connecting dialog
//       showDialog(
//         context: context,
//         barrierDismissible: false,
//         builder: (context) => const _ConnectingDialog(),
//       );

//       // Simulate connection attempt
//       await Future.delayed(const Duration(seconds: 2));

//       if (mounted) {
//         Navigator.of(context).pop(); // Close connecting dialog
//         widget.onNext();
//       }
//     }
//   }

//   @override
//   Widget build(BuildContext context) {
//     return Center(
//       child: Container(
//         constraints: const BoxConstraints(maxWidth: 600),
//         child: Column(
//           mainAxisAlignment: MainAxisAlignment.center,
//           children: [
//             // Icon with scanning animation
//             Stack(
//               alignment: Alignment.center,
//               children: [
//                 // Scanning circles
//                 if (_isScanning)
//                   AnimatedBuilder(
//                     animation: _scanAnimation,
//                     builder: (context, child) {
//                       return Container(
//                         width: 120 + (_scanAnimation.value * 40),
//                         height: 120 + (_scanAnimation.value * 40),
//                         decoration: BoxDecoration(
//                           shape: BoxShape.circle,
//                           border: Border.all(
//                             color: const Color(0xFF667EEA).withOpacity(0.3 - _scanAnimation.value * 0.3),
//                             width: 2,
//                           ),
//                         ),
//                       );
//                     },
//                   ),

//                 // Main icon
//                 Container(
//                   width: 80,
//                   height: 80,
//                   decoration: BoxDecoration(
//                     gradient: const LinearGradient(
//                       colors: [
//                         Color(0xFF667EEA),
//                         Color(0xFF764BA2),
//                       ],
//                     ),
//                     borderRadius: BorderRadius.circular(20),
//                     boxShadow: [
//                       BoxShadow(
//                         color: const Color(0xFF667EEA).withOpacity(0.3),
//                         blurRadius: 15,
//                         offset: const Offset(0, 5),
//                       ),
//                     ],
//                   ),
//                   child: const Icon(
//                     Icons.bluetooth,
//                     color: Colors.white,
//                     size: 40,
//                   ),
//                 ),
//               ],
//             ),

//             const SizedBox(height: 32),

//             // Title
//             const Text(
//               'Connect your device',
//               style: TextStyle(
//                 fontSize: 32,
//                 fontWeight: FontWeight.bold,
//                 color: Colors.white,
//               ),
//               textAlign: TextAlign.center,
//             ),

//             const SizedBox(height: 12),

//             // Subtitle
//             Text(
//               _isScanning ? 'Scanning for devices...' : 'Find and connect your Omi device',
//               style: TextStyle(
//                 fontSize: 16,
//                 color: Colors.grey.shade400,
//               ),
//               textAlign: TextAlign.center,
//             ),

//             const SizedBox(height: 48),

//             // Device list or scan button
//             Consumer<OnboardingProvider>(
//               builder: (context, provider, child) {
//                 if (provider.availableDevices.isEmpty && !_isScanning) {
//                   return _buildScanButton();
//                 } else if (_isScanning || provider.availableDevices.isNotEmpty) {
//                   return _buildDeviceList(provider.availableDevices);
//                 } else {
//                   return _buildScanButton();
//                 }
//               },
//             ),

//             const SizedBox(height: 48),

//             // Connect button (if device selected)
//             if (_selectedDevice != null)
//               Container(
//                 width: double.infinity,
//                 height: 56,
//                 decoration: BoxDecoration(
//                   gradient: const LinearGradient(
//                     colors: [
//                       Color(0xFF667EEA),
//                       Color(0xFF764BA2),
//                     ],
//                   ),
//                   borderRadius: BorderRadius.circular(16),
//                   boxShadow: [
//                     BoxShadow(
//                       color: const Color(0xFF667EEA).withOpacity(0.3),
//                       blurRadius: 12,
//                       offset: const Offset(0, 4),
//                     ),
//                   ],
//                 ),
//                 child: Material(
//                   color: Colors.transparent,
//                   child: InkWell(
//                     borderRadius: BorderRadius.circular(16),
//                     onTap: _connectDevice,
//                     child: const Center(
//                       child: Row(
//                         mainAxisSize: MainAxisSize.min,
//                         children: [
//                           Icon(
//                             Icons.link,
//                             color: Colors.white,
//                             size: 20,
//                           ),
//                           SizedBox(width: 8),
//                           Text(
//                             'Connect Device',
//                             style: TextStyle(
//                               fontSize: 18,
//                               fontWeight: FontWeight.w600,
//                               color: Colors.white,
//                             ),
//                           ),
//                         ],
//                       ),
//                     ),
//                   ),
//                 ),
//               ),

//             const SizedBox(height: 16),

//             // Skip for now
//             TextButton(
//               onPressed: widget.onNext,
//               child: Text(
//                 'Skip for now',
//                 style: TextStyle(
//                   color: Colors.grey.shade500,
//                   fontSize: 16,
//                 ),
//               ),
//             ),

//             const SizedBox(height: 24),

//             // Back button
//             TextButton(
//               onPressed: widget.onBack,
//               child: Text(
//                 'Back',
//                 style: TextStyle(
//                   color: Colors.grey.shade500,
//                   fontSize: 16,
//                 ),
//               ),
//             ),
//           ],
//         ),
//       ),
//     );
//   }

//   Widget _buildScanButton() {
//     return Container(
//       width: double.infinity,
//       height: 120,
//       decoration: BoxDecoration(
//         color: Colors.white.withOpacity(0.05),
//         borderRadius: BorderRadius.circular(16),
//         border: Border.all(
//           color: Colors.white.withOpacity(0.1),
//           width: 1,
//         ),
//       ),
//       child: Material(
//         color: Colors.transparent,
//         child: InkWell(
//           borderRadius: BorderRadius.circular(16),
//           onTap: _startScanning,
//           child: Column(
//             mainAxisAlignment: MainAxisAlignment.center,
//             children: [
//               Icon(
//                 Icons.bluetooth_searching,
//                 color: const Color(0xFF667EEA),
//                 size: 32,
//               ),
//               const SizedBox(height: 12),
//               const Text(
//                 'Scan for devices',
//                 style: TextStyle(
//                   fontSize: 16,
//                   fontWeight: FontWeight.w600,
//                   color: Colors.white,
//                 ),
//               ),
//               Text(
//                 'Turn on your Omi device first',
//                 style: TextStyle(
//                   fontSize: 12,
//                   color: Colors.grey.shade500,
//                 ),
//               ),
//             ],
//           ),
//         ),
//       ),
//     );
//   }

//   Widget _buildDeviceList(List<BTDeviceStruct> devices) {
//     return Container(
//       constraints: const BoxConstraints(maxHeight: 300),
//       child: Column(
//         children: [
//           // Scan controls
//           Row(
//             mainAxisAlignment: MainAxisAlignment.spaceBetween,
//             children: [
//               Text(
//                 'Available devices (${devices.length})',
//                 style: const TextStyle(
//                   fontSize: 16,
//                   fontWeight: FontWeight.w600,
//                   color: Colors.white,
//                 ),
//               ),
//               TextButton.icon(
//                 onPressed: _isScanning ? _stopScanning : _startScanning,
//                 icon: Icon(
//                   _isScanning ? Icons.stop : Icons.refresh,
//                   size: 16,
//                 ),
//                 label: Text(_isScanning ? 'Stop' : 'Rescan'),
//                 style: TextButton.styleFrom(
//                   foregroundColor: const Color(0xFF667EEA),
//                 ),
//               ),
//             ],
//           ),

//           const SizedBox(height: 16),

//           // Device list
//           Expanded(
//             child: ListView.builder(
//               itemCount: devices.length,
//               itemBuilder: (context, index) {
//                 final device = devices[index];
//                 final isSelected = _selectedDevice?.id == device.id;

//                 return Container(
//                   margin: const EdgeInsets.only(bottom: 12),
//                   decoration: BoxDecoration(
//                     color: isSelected ? const Color(0xFF667EEA).withOpacity(0.2) : Colors.white.withOpacity(0.05),
//                     borderRadius: BorderRadius.circular(12),
//                     border: Border.all(
//                       color: isSelected ? const Color(0xFF667EEA) : Colors.white.withOpacity(0.1),
//                       width: isSelected ? 2 : 1,
//                     ),
//                   ),
//                   child: ListTile(
//                     leading: Container(
//                       width: 40,
//                       height: 40,
//                       decoration: BoxDecoration(
//                         color: const Color(0xFF667EEA).withOpacity(0.2),
//                         borderRadius: BorderRadius.circular(8),
//                       ),
//                       child: const Icon(
//                         Icons.device_hub,
//                         color: Color(0xFF667EEA),
//                         size: 20,
//                       ),
//                     ),
//                     title: Text(
//                       device.name,
//                       style: TextStyle(
//                         color: isSelected ? Colors.white : Colors.grey.shade300,
//                         fontWeight: isSelected ? FontWeight.w600 : FontWeight.normal,
//                       ),
//                     ),
//                     subtitle: Text(
//                       'Battery: ${device.batteryLevel}%',
//                       style: TextStyle(
//                         color: Colors.grey.shade500,
//                         fontSize: 12,
//                       ),
//                     ),
//                     trailing: isSelected
//                         ? const Icon(
//                             Icons.check_circle,
//                             color: Color(0xFF667EEA),
//                           )
//                         : null,
//                     onTap: () => _selectDevice(device),
//                   ),
//                 );
//               },
//             ),
//           ),
//         ],
//       ),
//     );
//   }
// }

// class _ConnectingDialog extends StatelessWidget {
//   const _ConnectingDialog();

//   @override
//   Widget build(BuildContext context) {
//     return AlertDialog(
//       backgroundColor: const Color(0xFF1A1A1A),
//       shape: RoundedRectangleBorder(
//         borderRadius: BorderRadius.circular(16),
//       ),
//       content: const SizedBox(
//         width: 300,
//         child: Column(
//           mainAxisSize: MainAxisSize.min,
//           children: [
//             CircularProgressIndicator(
//               valueColor: AlwaysStoppedAnimation<Color>(Color(0xFF667EEA)),
//             ),
//             SizedBox(height: 24),
//             Text(
//               'Connecting to device...',
//               style: TextStyle(
//                 color: Colors.white,
//                 fontSize: 16,
//               ),
//               textAlign: TextAlign.center,
//             ),
//             SizedBox(height: 8),
//             Text(
//               'This may take a few moments.',
//               style: TextStyle(
//                 color: Colors.grey,
//                 fontSize: 14,
//               ),
//               textAlign: TextAlign.center,
//             ),
//           ],
//         ),
//       ),
//     );
//   }
// }
