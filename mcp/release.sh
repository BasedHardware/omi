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

#uv sync
#uv build
#uv publish
#uv cache clean; uv cache prune

# # ----

# Log in to Docker Hub using an access token
echo "$DOCKER_ACCESS_TOKEN" | docker login -u omiai --password-stdin

docker build -t omiai/mcp-server .
docker push omiai/mcp-server:$new_version
docker push omiai/mcp-server:latest
