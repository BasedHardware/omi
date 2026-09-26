I'll start by exploring the repository structure to understand what actually exists before producing any code.

<tool_call>
<function=Bash>
<parameter=command>
ls -la && echo "---GIT---" && git log --oneline -5 2>/dev/null && echo "---REMOTE---" && git remote -v 2>/dev/null
</parameter>
<parameter=description>
List repo root and git info
</parameter>
</function>
</tool_call>