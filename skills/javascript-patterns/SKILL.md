---
name: javascript-patterns
description: Modern JavaScript (ES2020+) idioms and pitfalls for browser and Node code, covering equality, immutability, async iteration, modules, optional chaining, and common traps. Use when writing or reviewing plain JavaScript, not TypeScript.
---

# JavaScript Patterns

## Equality and coercion
- Use `===` and `!==`. The one exception is `== null` to test for both `null` and `undefined`.
- `NaN` is not equal to itself. Use `Number.isNaN(x)`, not `x === NaN` or global `isNaN`.

## Scope
- Use `const` by default, `let` when reassigned. Avoid `var`.
- Closures in loops: `let` in a `for` loop binds per iteration; `var` does not.

## Immutability
- Return new arrays and objects from transformations: `[...items, next]`, `{...user, name}`.
- `Object.freeze` is shallow. Freeze nested objects separately or avoid mutation by convention.
- `structuredClone(obj)` copies nested data, but it drops functions and class prototypes.

## Optional values
- `?.` and `??` short-circuit on `null` and `undefined` only. `0` and `''` are kept by `??`, dropped by `||`.

```js
const port = config.port ?? 3000; // 0 stays 0
const port2 = config.port || 3000; // 0 becomes 3000
```

## Arrays
- `Array.prototype.sort` sorts in place and compares strings by default. Pass a comparator: `(a, b) => a - b`.
- `map(parseInt)` passes the index as the radix. Use `map(Number)` or `map((s) => parseInt(s, 10))`.
- Use `Object.groupBy` only where the target runtime supports it; check the engine table first.

## Async
- `forEach` does not await async callbacks. Use `for...of` with `await`, or `Promise.all` with `map`.
- Async iteration: `for await (const chunk of stream)`.

## Modules
- Named exports for most code. Keep one default export per module at most.
- Avoid circular imports. If two modules import each other, move the shared piece to a third module.

## Date and numbers
- `Date` months are zero-based. Store timestamps as ISO 8601 UTC strings or epoch milliseconds.
- Floating point: `0.1 + 0.2 !== 0.3`. Use integer cents for money.

## Review checklist
- No accidental globals (`'use strict'` or ES modules).
- No `eval` or `new Function` on input.
- Every `catch` names the error or explains why it is ignored.
