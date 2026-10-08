# Node.js rules

- Await every promise. No floating promises.
- Every outbound call has a timeout (`AbortSignal.timeout` with fetch).
- Validate environment variables once at startup; fail fast naming the missing variable.
- Use `execFile` or `spawn` with an argument array. Never `exec` with interpolated input.
- Commit the lockfile. CI installs with `npm ci`.
- Check the Node version in `package.json` `engines` or `.nvmrc` before using newer APIs.
- Confirm a new package exists with `npm view <name> version` before importing it.
