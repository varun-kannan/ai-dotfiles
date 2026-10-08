# Security rules

- Parameterized queries only. Never build SQL, shell commands, or HTML by string concatenation with input.
- Validate and normalize input at the trust boundary. Reject unexpected types; do not silently coerce.
- Resolve a user-supplied path and confirm it stays inside the intended root before reading or writing.
- No keys, tokens, passwords, or personal data in source, tests, fixtures, or logs.
- Log structured fields. Strip newlines and control characters from user-supplied values in logs.
- Use the platform crypto library. No hand-rolled crypto. No MD5 or SHA-1 for security.
- Token generation uses a cryptographically secure random source.
- Authorization is checked on the server for each object accessed.
- No `eval`, no `exec` or `shell=True` on anything influenced by a user.
- Changes to auth, crypto, paths, subprocesses, or deserialization: say so in the summary so a human reviews them.
