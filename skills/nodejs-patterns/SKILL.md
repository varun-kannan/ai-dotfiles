---
name: nodejs-patterns
description: Node.js server and tooling patterns covering async control flow, streams, error handling at process boundaries, configuration, graceful shutdown, and package hygiene. Use when writing or reviewing Node.js services, CLIs, or scripts.
---

# Node.js Patterns

Confirm the Node version from `package.json` `engines` or `.nvmrc` before using a newer API.

## Async
- Await every promise you create. A floating promise hides its failure.
- Run independent work in parallel with `Promise.all`. Use `Promise.allSettled` when one failure must not drop the others.
- Bound concurrency for large lists. Plain `Promise.all` over 10,000 items opens 10,000 requests. Use a small pool or a library already in the repo.
- Use `AbortSignal.timeout(ms)` with `fetch` to bound outbound calls.

```js
const res = await fetch(url, { signal: AbortSignal.timeout(5000) });
if (!res.ok) throw new Error(`upstream ${res.status} for ${url}`);
```

## Errors at boundaries
- Register `process.on('unhandledRejection')` only to log and exit. Do not keep running after an unknown failure.
- In an HTTP handler, convert known errors to status codes in one middleware. Log unknown errors once.

## Streams
- Use `stream.pipeline` (or `pipeline` from `stream/promises`) so errors propagate and resources close.
- Do not read a large file into memory with `readFile` when a stream fits.

## Configuration
- Read environment variables once at startup, validate, and export a typed config object. Do not read `process.env` throughout the code.
- Fail fast on a missing required variable with the variable's name in the message.

## Shutdown
- On `SIGTERM`, stop accepting new connections, finish in-flight requests with a deadline, close database pools, then exit.

## Modules and packages
- Check the module system in `package.json` (`"type": "module"`). Do not mix `require` and `import` in one file without reason.
- Commit the lockfile. Use `npm ci` in CI.
- Before adding a package, run `npm view <name> version` and check its maintenance status.

## Security
- Never pass user input to `child_process.exec`. Use `execFile` or `spawn` with an argument array.
- Use `path.resolve` plus a prefix check before serving or reading user-named files.
