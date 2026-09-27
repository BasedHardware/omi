import re

with open("app/lib/backend/http/api/conversations.dart", "r") as f:
    content = f.read()

# Replace StatusResponse with wire.GeneratedStatusResponse
replacement = """    final statusResponse = wire.GeneratedStatusResponse.fromJson(jsonDecode(response.body) as Map<String, dynamic>);
    final status = statusResponse.status;
    return status == 'unchanged' ? CaptureGroupSeparationResult.unchanged : CaptureGroupSeparationResult.separated;"""

pattern = r"""    final statusResponse = StatusResponse\.fromJson\(jsonDecode\(response\.body\)\);
    final status = statusResponse\.status;
    return status == 'unchanged' \? CaptureGroupSeparationResult\.unchanged : CaptureGroupSeparationResult\.separated;"""

new_content = re.sub(pattern, replacement, content)

with open("app/lib/backend/http/api/conversations.dart", "w") as f:
    f.write(new_content)
