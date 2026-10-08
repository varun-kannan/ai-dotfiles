---
name: typescript-patterns
description: TypeScript type design and strictness patterns, covering strict config, narrowing unknown input, discriminated unions, branded types, exhaustive checks, and avoiding any. Use when writing or reviewing TypeScript code or tsconfig settings.
---

# TypeScript Patterns

## Configuration
- Enable `"strict": true`. Also consider `"noUncheckedIndexedAccess": true` for array and record access.
- Check the compiler version in `package.json` before using newer syntax such as `satisfies` (TypeScript 4.9+).

## Input is unknown
- Type external input as `unknown`, then narrow. Never cast with `as` to skip validation.
- Validate at the boundary with a schema library already in the project (zod, valibot) or with type guards.

```ts
function isUser(value: unknown): value is User {
  return typeof value === 'object' && value !== null && 'id' in value && typeof value.id === 'string';
}
```

## Model states with unions
- Use a discriminated union so impossible states cannot be written.

```ts
type Load =
  | { status: 'idle' }
  | { status: 'loading' }
  | { status: 'ok'; data: Order[] }
  | { status: 'error'; message: string };
```

- Exhaustive switch: add a `default` that assigns to `never` so a new variant fails compilation.

```ts
function assertNever(x: never): never {
  throw new Error(`unhandled: ${JSON.stringify(x)}`);
}
```

## Avoiding any
- `any` disables checking for everything it touches. Use `unknown` when the type is truly unknown.
- Lint with `@typescript-eslint/no-explicit-any` if the project already runs ESLint.

## Branded types for IDs
- Stop passing a `UserId` where an `OrderId` is expected, when both are strings.

```ts
type UserId = string & { readonly __brand: 'UserId' };
```

## Generics
- Add a generic only when two or more call sites need different types. Otherwise write the concrete type.

## Declarations
- Prefer `type` for unions and object shapes, `interface` for shapes meant to be extended or implemented by classes. Be consistent with the repo.
- Use `import type` for type-only imports when `verbatimModuleSyntax` or `isolatedModules` is set.

## Common mistakes
- Optional property vs `undefined` value: `{ a?: string }` allows missing; `{ a: string | undefined }` requires the key.
- Non-null assertion `!` hides a real null path. Narrow instead.
- Enums: prefer string literal unions unless the repo uses enums already.
