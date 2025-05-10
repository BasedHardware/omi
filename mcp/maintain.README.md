### Minor docs for maintaing

**Development**

- understand uv https://docs.astral.sh/uv/
- When developing locally the mcp
  - launch the inspector `npx @modelcontextprotocol/inspector`
  - when testing in the dashboard, set command `uv`, args `run mcp-server-omi -v`
  - if you do `uvx` + `mcp-server-omi`, you would be pointing towards the deployed package.
  - If you make any changes to the package, and want to test, just refresh the inspector dashboard, connect again, test.
  - An alternative to `uv run`, is `python -m mcp_server_omi`
- what's uvx? a simpler way to execute a python package without installing it.
- If wanting to test a more real version of the MCP, modify the claude dekstop config to run your package, you should do either `uv run` (pointing locally) or `python -m`, restart claude, and check the tools available (https://modelcontextprotocol.io/examples)
- Tools are wrapping around `backend/routers/mcp.py` routes directly on main backend.

**Releasing**
Run `sh release.sh` this will upgrade the version in `__about__.py`, publish to pypi, build and deploy the `Dockerfile` as well.

(Dockerfile might be on Joan's account, switch to Omi organization)


**Next Steps**
- [ ] Check TODO's
- [ ] Improve retrieval so that conversation retrieval can have QA sort of
- [ ] Connect authentication / key handling (@thinh?)