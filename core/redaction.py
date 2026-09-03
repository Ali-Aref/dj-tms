import re


REDACTED = "[REDACTED]"
_SENSITIVE_KEYS = {"pin", "pinblock", "cvv", "track2", "ksn", "authorization", "bearer", "apikey"}
_KEY_VALUE = re.compile(
    r'''(?i)(["']?(?:pin(?:block)?|cvv|track2|ksn|authorization|bearer|api[_ -]?key|[a-z0-9_-]*(?:token|secret|password))["']?\s*[:=]\s*)(?:bearer\s+[a-z0-9._~+/=-]+|"[^"]*"|'[^']*'|[^\s,;}&]+)'''
)
_BEARER = re.compile(r"(?i)\bbearer\s+[a-z0-9._~+/=-]+")
_PAN = re.compile(r"(?<!\d)(?:\d[ -]?){12,18}\d(?!\d)")


def _sensitive_key(key):
    normalized = re.sub(r"[^a-z0-9]", "", str(key).lower())
    return normalized in _SENSITIVE_KEYS or normalized.endswith(("token", "secret", "password"))


def redact_text(value):
    if not isinstance(value, str):
        return value
    value = _KEY_VALUE.sub(lambda match: match.group(1) + REDACTED, value)
    value = _BEARER.sub("Bearer " + REDACTED, value)
    return _PAN.sub(REDACTED, value)


def redact_obj(value):
    if isinstance(value, dict):
        return {
            key: REDACTED if _sensitive_key(key) else redact_obj(item)
            for key, item in value.items()
        }
    if isinstance(value, list):
        return [redact_obj(item) for item in value]
    return redact_text(value)
