# Get current version from __about__.py
current_version=$(grep -o '".*"' src/mcp_server_omi/__about__.py | tr -d '"')
echo "Current version: $current_version"

# Split version into parts
IFS='.' read -r major minor patch <<< "$current_version"

# Increment patch version
new_patch=$((patch + 1))
new_version="$major.$minor.$new_patch"
echo "New version: $new_version"

# Update version in __about__.py
sed -i '' "s/__version__ = \".*\"/__version__ = \"$new_version\"/" src/mcp_server_omi/__about__.py

# -----

uv sync
uv build
uv publish
uv cache clean; uv cache prune

# # ----

docker build -t josancamon19/mcp-server-omi .
docker push josancamon19/mcp-server-omi
