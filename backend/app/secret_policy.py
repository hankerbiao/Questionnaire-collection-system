UNSAFE_SECRETS = frozenset({
    "change-me-in-production",
    "replace-with-at-least-32-random-characters",
    "replace-with-another-32-character-random-secret",
    "replace-with-a-user-session-random-secret",
    "use-a-different-at-least-32-character-secret",
})


def configured_secret(value: str) -> bool:
    """Accept only non-public secrets with enough entropy-bearing length."""
    return len(value) >= 32 and value not in UNSAFE_SECRETS
