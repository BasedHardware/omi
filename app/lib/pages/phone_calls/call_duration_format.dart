String formatPhoneCallDuration(Duration d) {
  String twoDigits(int n) => n.toString().padLeft(2, '0');
  if (d.inHours > 0) {
    return '${twoDigits(d.inHours)}:${twoDigits(d.inMinutes.remainder(60))}:${twoDigits(d.inSeconds.remainder(60))}';
  }
  return '${twoDigits(d.inMinutes)}:${twoDigits(d.inSeconds.remainder(60))}';
}
