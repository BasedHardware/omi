```
--- 
plugins/omi-hive-app/hive.py
+++ 
plugins/omi-hive-app/hive.py
@@ -1,4 +1,4 @@
-from __future__ import annotations
+from __future__ import annotations
 from typing import Optional, Dict, Any
 from ..base import Base
 import logging
@@ -14,12 +14,12 @@
     @property
     def verify_api_key(self) -> bool:
         try:
-            logging.info(f"Verifying API key: {self._api_key}")
+            logging.info("Verifying API key")
             response = self._api_request("GET", "https://api.hive.io/v1/verify_api_key", {"api_key": self._api_key})
             return response.get("ok", False)
         except Exception as e:
-            logging.error(f"Error verifying API key: {str(e)}")
+            logging.error(f"Error verifying API key: {type(e).__name__}")
             return False
```

```
--- 
plugins/omi-hive-app/hive.py
+++ 
plugins/omi-hive-app/hive.py
@@ -144,12 +144,12 @@
     def get_user_workspaces(self) -> Dict[str, Any]:
         try:
             response = self._api_request("GET", "https://api.hive.io/v1/user/workspaces", {"user_id": self._user_id})
             return response
         except Exception as e:
-            logging.error(f"Error getting user workspaces: {str(e)}")
+            logging.error(f"Error getting user workspaces: {type(e).__name__}")
             return {"error": str(e)}
```

```
--- 
plugins/omi-hive-app/hive.py
+++ 
plugins/omi-hive-app/hive.py
@@ -178,10 +178,11 @@
             result = self._api_request(method, url, params)
         except Exception as e:
-            logging.error(f"REST API request failed: {str(e)}")
+            logging.error(f"REST API request failed: {type(e).__name__}")
             result = {"error": "Request failed. Please try again."}
         return result
 
     def hive_graphql_request(self, query: str, variables: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
```

```
--- 
.github/checks-manifest.yaml
+++ 
.github/checks-manifest.yaml
@@ -1,3 +1,4 @@
 checks:
   hive-app:
     path: plugins/omi-hive-app
+  hive-app-error-handling-tests:
+    path: tests/integration/hive_app_error_handling
```