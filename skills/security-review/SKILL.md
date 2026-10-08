---
name: security-review
description: Application security review against the OWASP Top 10 and common CWEs. Use when changing authentication, authorization, input handling, file paths, subprocess calls, SQL, HTML output, crypto, secrets, logging, or dependencies.
---

# Security Review

Read the changed code and every caller of changed functions. Report only defects you traced to a line.

## Input and output
- SQL: parameterized queries only. Never build SQL by concatenation or f-string.
- Shell: pass arguments as a list, not a string. Never `shell=True` or `exec` with user text.
- HTML: escape by context. Use the framework's auto-escaping. Avoid `innerHTML` and `dangerouslySetInnerHTML` with untrusted data.
- Paths: resolve the joined path and confirm it stays under the root (`realpath` and prefix check). Reject `..` and absolute input.
- Validate and normalize at the trust boundary. Reject, do not silently fix, unexpected types.

## Auth and access
- Check authorization on the server for every object access, using the resource's owner, not a client-supplied ID alone (IDOR).
- Verify tokens: signature, expiry, audience, issuer. Reject `alg: none`.
- Compare secrets with constant-time comparison.
- Session cookies: `HttpOnly`, `Secure`, `SameSite`.

## Secrets and logging
- No keys, tokens, or passwords in source, tests, fixtures, or logs.
- Log structured fields. Strip or encode newlines and control characters in user-supplied values to prevent log injection.
- Never log request bodies that may contain credentials.

## Crypto
- Use the platform library: `secrets` or `crypto.randomBytes` for tokens, `bcrypt`, `scrypt`, or `argon2` for passwords, AES-GCM or ChaCha20-Poly1305 for encryption.
- No MD5 or SHA-1 for security. No fixed IVs or nonces. No `Math.random` or `random` for tokens.

## Deserialization
- No `pickle` or `yaml.load` without a safe loader on untrusted data. No Java native deserialization of untrusted bytes.

## Dependencies
- Before accepting a new package, confirm it exists in the registry (`npm view`, `pip index versions`, `cargo search`). Check it is maintained.

## Output format
`severity | file:line | attack path in one sentence | fix`. End with "Human review required" when auth, crypto, paths, subprocesses, or deserialization changed.
