import 'package:flutter/widgets.dart';

import 'package:font_awesome_flutter/font_awesome_flutter.dart';

/// Maps folder icon strings (emojis) to FontAwesome IconData.
/// Falls back to a folder icon for unknown values.
IconData folderIconToFa(String? iconString) {
  return _emojiToFaMap[iconString] ?? FontAwesomeIcons.folder.data;
}

/// Mapping from emoji strings to FontAwesome icons.
Map<String, IconData> _emojiToFaMap = {
  '📁': FontAwesomeIcons.solidFolder.data,
  '💼': FontAwesomeIcons.briefcase.data,
  '🏠': FontAwesomeIcons.solidHouse.data,
  '📚': FontAwesomeIcons.book.data,
  '👨‍👩‍👧‍👦': FontAwesomeIcons.users.data,
  '👤': FontAwesomeIcons.solidHeart.data,
  '👥': FontAwesomeIcons.users.data,
  '❤️': FontAwesomeIcons.solidHeart.data,
  '🎮': FontAwesomeIcons.gamepad.data,
  '✈️': FontAwesomeIcons.plane.data,
  '🏥': FontAwesomeIcons.solidHospital.data,
  '🛒': FontAwesomeIcons.cartShopping.data,
  '💰': FontAwesomeIcons.moneyBill.data,
  '🎵': FontAwesomeIcons.music.data,
  '🎨': FontAwesomeIcons.palette.data,
  '📝': FontAwesomeIcons.pen.data,
  '💬': FontAwesomeIcons.solidComments.data,
  '🌎': FontAwesomeIcons.globe.data,
  '🛠️': FontAwesomeIcons.screwdriverWrench.data,
  '🍔': FontAwesomeIcons.burger.data,
  '🏆': FontAwesomeIcons.trophy.data,
  '🔒': FontAwesomeIcons.lock.data,
  '⭐': FontAwesomeIcons.solidStar.data,
  '🕐': FontAwesomeIcons.solidClock.data,
  '📊': FontAwesomeIcons.chartSimple.data,
};

/// List of all available folder icon strings (for use in icon picker UI).
const List<String> folderIconStrings = [
  '📁',
  '💼',
  '🏠',
  '📚',
  '👨‍👩‍👧‍👦',
  '❤️',
  '🎮',
  '✈️',
  '🏥',
  '🛒',
  '💰',
  '🎵',
  '🎨',
  '📝',
  '💬',
  '🌎',
  '🛠️',
  '🍔',
  '🏆',
  '🔒',
];
