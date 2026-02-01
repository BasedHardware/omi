---
name: browser-automation
description: "Browser testing, design-to-code conversion, accessibility auditing, and visual debugging. Use for web development, testing, and design implementation."
---

# Browser Automation Skill

Browser automation capabilities for testing, design-to-code, accessibility auditing, and visual debugging.

## When to Use

Use this skill when:
- Testing web applications
- Converting designs to code
- Auditing accessibility
- Visual debugging
- Automated testing workflows

## Capabilities

### Testing

- Navigate to URLs
- Click elements
- Type in inputs
- Scroll pages
- Capture screenshots
- Read console output
- Monitor network traffic

### Design to Code

- Analyze design mockups
- Generate HTML/CSS code
- Match layouts, colors, spacing
- Use design sidebar for adjustments

### Accessibility

- WCAG compliance checks
- Color contrast verification
- Semantic HTML validation
- Keyboard navigation testing

## Workflows

### Testing Applications

```
@browser Test the login flow:
1. Navigate to /login
2. Fill in email and password
3. Click submit
4. Verify redirect to dashboard
5. Check for console errors
```

### Design to Code

```
@browser Analyze this design mockup and generate the HTML/CSS code
```

### Accessibility Auditing

```
@browser Check accessibility:
- Color contrast ratios
- Semantic HTML
- ARIA labels
- Keyboard navigation
```

## Security

- Browser tools require manual approval by default
- Configure allow/block lists in settings
- Never use auto-run with untrusted code

## Related Resources

- Rule: `.cursor/rules/agent-browser.mdc`
- Commands: `/browser-test`, `/accessibility-audit`
- Agent: `.cursor/skills/browser-automation/agents/browser-automation.md`
