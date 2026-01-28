# Browser Test

Use browser automation to test web applications, verify UI changes, and validate workflows.

## Usage

```
@browser Test the login flow:
1. Navigate to /login
2. Fill in email and password
3. Click submit
4. Verify redirect to dashboard
5. Check for console errors
```

## Capabilities

- **Navigate**: Go to URLs
- **Click**: Interact with elements
- **Type**: Fill in forms
- **Scroll**: Navigate pages
- **Screenshot**: Capture page state
- **Console**: Read JavaScript errors
- **Network**: Monitor requests

## Testing Workflows

### Form Validation

```
@browser Test form validation:
1. Navigate to /signup
2. Submit empty form
3. Verify error messages
4. Fill required fields
5. Submit and verify success
```

### User Flows

```
@browser Test checkout flow:
1. Add item to cart
2. Go to checkout
3. Fill shipping info
4. Select payment method
5. Complete purchase
6. Verify confirmation page
```

### Responsive Design

```
@browser Test responsive design:
1. Set viewport to mobile (375x667)
2. Navigate to homepage
3. Verify layout adapts
4. Test navigation menu
5. Check for horizontal scroll
```

## Best Practices

1. **Be specific**: Clear steps and expected outcomes
2. **Test edge cases**: Empty forms, invalid inputs
3. **Check console**: Monitor for JavaScript errors
4. **Verify workflows**: Complete user flows end-to-end
5. **Test responsive**: Different screen sizes

## Security

- Browser actions require approval by default
- Review each action before execution
- Configure allow lists for trusted actions

## Related Resources

- Skill: `.cursor/skills/browser-automation/SKILL.md`
- Agent: `.cursor/skills/browser-automation/agents/browser-automation.md`
- Rule: `.cursor/rules/agent-browser.mdc`
