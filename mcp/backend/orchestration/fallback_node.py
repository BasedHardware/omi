from orchestration.state import AgentState
def _get_fallback_response(state: AgentState) -> AgentState:
        return """I cannot assist with that request. I'm here to help with robotics club activities like:

• Answering technical questions about robotics, programming, and control systems
• Searching for code examples and research papers
• Finding relevant repositories and documentation
• Scheduling meetings and workshops
• Managing email communication and calendar events

How can I help you with these tasks?"""