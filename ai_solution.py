To solve this problem, we need to ensure that the function correctly handles both naive and aware datetime values for the configured expiry. The function should return `(False, 'expired')` when the expiry date has passed, considering both date and datetime formats.

### Approach

1. **Check for the feature being enabled**: The function first checks if the feature is enabled by verifying `CAPTURE_JEV_SHADOW_ENABLED`.
2. **Parse the configured expiry**: The configured expiry is parsed, and if it's a date, it is converted to a naive datetime.
3. **Determine the current time and hard stop**: The current time (`now()`) is determined, and the hard stop is set to one day from now.
4. **Calculate the expiry**: The minimum of the configured expiry and the hard stop is taken.
5. **Check if the expiry has passed**: If the expiry is on or before the current time, the function returns `(False, 'expired')`.
6. **Return the result**: If the feature is enabled and not expired, it returns `(True, None)`.

### Solution Code

```python
def capture_jev_shadow_enabled():
    if not CAPTURE_JEV_SHADOW_ENABLED:
        return (False, "shadow disabled")
    try:
        configured = parse(CAPTURE_JEV_SHADOW_EXPIRY)
    except (ValueError, TypeError):
        configured = now()
    now_ = now()
    hard_stop = now() + timedelta(days=1)
    # Convert date to naive datetime for comparison
    if configured.tzinfo is None:
        configured = configured.date()
    expiry = min(configured, hard_stop)
    if expiry <= now_:
        return (False, "expired")
    return (True, None)
```