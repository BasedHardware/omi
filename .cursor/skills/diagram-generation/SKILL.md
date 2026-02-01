---
name: diagram-generation
description: "Mermaid diagram generation for architecture visualization, data flow diagrams, and component relationships. Use for documentation, PR descriptions, and architectural analysis."
---

# Diagram Generation Skill

Generate Mermaid diagrams to visualize architecture, data flows, and component relationships.

## When to Use

Use this skill when:
- Documenting architecture
- Explaining complex changes in PRs
- Visualizing data flows
- Understanding component relationships
- Revealing architectural issues

## Capabilities

### Architecture Diagrams

- System architecture
- Component relationships
- Service interactions
- Module dependencies

### Data Flow Diagrams

- Request/response flows
- Data transformation pipelines
- State management flows
- Event flows

### Sequence Diagrams

- API call sequences
- User interaction flows
- Process workflows
- Error handling flows

## Usage

```
Create a Mermaid diagram showing the data flow for our authentication system,
including OAuth providers, session management, and token refresh.
```

## Best Practices

1. **Be specific**: Describe what you want to visualize
2. **Include context**: Mention relevant files or components
3. **Review diagrams**: Verify accuracy and completeness
4. **Use in docs**: Add diagrams to documentation
5. **Update regularly**: Keep diagrams current with code

## Related Resources

- Rule: `.cursor/rules/large-codebase-patterns.mdc`
- Command: `/diagram`
- Agent: `.cursor/skills/diagram-generation/agents/diagram-generator.md`
