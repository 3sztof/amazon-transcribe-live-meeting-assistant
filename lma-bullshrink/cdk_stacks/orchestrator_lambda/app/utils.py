def sanitize_key_prefix(raw_call_id: str) -> str:
    """
    Sanitize the call ID for use as a key prefix

    Args:
        call_id: The raw call ID
    Returns:
        str: Sanitized key prefix
    """
    return (
        raw_call_id.replace(" ", "_")
        .replace("-", "_")
        .replace(":", "_")
        .replace(",", "_")
    )
