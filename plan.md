1. **Add `httpx` to `requirements.txt`**
   - We need `httpx` for asynchronous HTTP requests to replace synchronous blocking `requests`.
   - Update `plugins/omi-dropbox-app/requirements.txt` with `httpx>=0.25.0`.
2. **Update imports in `main.py`**
   - Add `import httpx` at the top of `plugins/omi-dropbox-app/main.py`.
3. **Refactor blocking I/O to async in `main.py`**
   - In `auth_callback` (around line 484), replace the synchronous `requests.post` call with an async `httpx.AsyncClient().post`.
   - This optimization significantly improves throughput when multiple requests are received by freeing the event loop.
4. **Complete pre commit steps**
   - Ensure proper testing, verification, review, and reflection are done.
5. **Submit the change**
   - Once all tests pass, submit the change with a descriptive commit message detailing the performance improvement.
