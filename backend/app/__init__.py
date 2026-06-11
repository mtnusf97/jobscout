"""JobScout backend.

Use the OS trust store for TLS so outbound HTTPS works on machines behind
TLS-inspecting proxies (Zscaler etc.) whose root CA lives in the system keychain
but not in Python's bundled CA list.
"""

try:
    import truststore

    truststore.inject_into_ssl()
except ImportError:  # pragma: no cover - truststore is in requirements
    pass
