---
name: react-patterns
description: React component design covering hooks rules, state placement, effects, memoization, data fetching, composition, keys, and testing with Testing Library. Use when writing or reviewing React components or hooks.
---

# React Patterns

Confirm the React version in `package.json` first. Hook and server-component behavior differs between major versions.

## Hooks rules
- Call hooks at the top level of a component or custom hook. Never inside conditions or loops.
- Custom hooks start with `use` and return a stable shape.

## State placement
- Keep state in the lowest component that needs it. Lift it only when two siblings share it.
- Derive values during render instead of storing them: `const total = items.reduce(...)`, not `useState` plus an effect.
- Server data (fetched lists, user profile) belongs in a data-fetching layer such as TanStack Query or the framework's loader, not hand-written `useEffect` fetches, when the project already uses one.

## Effects
- An effect synchronizes with something outside React: a subscription, a timer, a DOM API, a network request that has no other owner.
- Return a cleanup for subscriptions and timers.
- Do not use an effect to respond to a state change that an event handler could handle directly.
- Race conditions in fetches: use an `ignore` flag or `AbortController` in cleanup.

```tsx
useEffect(() => {
  const controller = new AbortController();
  fetch(url, { signal: controller.signal }).then(...).catch(...);
  return () => controller.abort();
}, [url]);
```

## Memoization
- `useMemo` and `useCallback` only when a measured render cost or a stable reference for a memoized child matters. Otherwise they add noise.
- `React.memo` a child only after profiling shows it re-renders needlessly.

## Keys
- Keys must be stable and unique among siblings. Never use the array index for a list that reorders, inserts, or filters.

## Composition
- Pass children or slots instead of configuration props for layout: `<Card header={...}>` over `<Card showHeader titleText ...>`.
- Split a component when it has two reasons to change. Do not split it into one-use fragments.

## Accessibility
- Use native elements: `<button>` for actions, `<a href>` for navigation. Do not put `onClick` on a `div` without role, keyboard handling, and focus.

## Testing
- Query by role and visible text (`getByRole`, `getByLabelText`). Avoid test IDs unless no accessible query exists.
- Test behavior: click, type, see the result. Do not assert internal state or hook calls.
