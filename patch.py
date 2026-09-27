import re

with open("app/lib/backend/http/api/conversations.dart", "r") as f:
    content = f.read()

# Replace jsonDecode and body is Map with StatusResponse generated model
replacement = """    final statusResponse = StatusResponse.fromJson(jsonDecode(response.body));
    final status = statusResponse.status;
    return status == 'unchanged' ? CaptureGroupSeparationResult.unchanged : CaptureGroupSeparationResult.separated;"""

pattern = r"""    final body = jsonDecode\(response\.body\);
    final status = body is Map \? body\['status'\] : null;
    return status == 'unchanged' \? CaptureGroupSeparationResult\.unchanged : CaptureGroupSeparationResult\.separated;"""

new_content = re.sub(pattern, replacement, content)

with open("app/lib/backend/http/api/conversations.dart", "w") as f:
    f.write(new_content)
