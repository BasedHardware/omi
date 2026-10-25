with open('app/lib/utils/logger.dart', 'r') as f:
    lines = f.readlines()

with open('app/lib/utils/logger.dart', 'w') as f:
    for line in lines:
        if "import 'package:intercom_flutter/intercom_flutter.dart';" not in line:
            f.write(line)
