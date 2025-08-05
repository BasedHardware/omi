"""
Generic framework path manipulation
"""

__all__ = ["infoForFramework"]

# This regexp should find:
#   \1 - framework location
#   \2 - framework name
#   \3 - framework version (optional)
#
FRAMEWORK_RE_STR = r"""(^.*)(?:^|/)(\w+).framework(?:/(?:Versions/([^/]+)/)?\2)?$"""
FRAMEWORK_RE = None


def infoForFramework(filename):
    """returns (location, name, version) or None"""
    global FRAMEWORK_RE
    if FRAMEWORK_RE is None:
        import re

        FRAMEWORK_RE = re.compile(FRAMEWORK_RE_STR)
    is_framework = FRAMEWORK_RE.findall(filename)
    if not is_framework:
        return None
    return is_framework[-1]
