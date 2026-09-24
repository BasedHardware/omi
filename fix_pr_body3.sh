OLD_LINES=$(git show origin/main:backend/routers/apps.py | wc -l)
NEW_LINES=$(wc -l < backend/routers/apps.py)
echo "Line-Count-Exception: backend/routers/apps.py | ${OLD_LINES} -> ${NEW_LINES} | added rejection reason to apps"
