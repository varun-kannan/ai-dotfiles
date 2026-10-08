---
name: accessibility-guide
description: Web and app accessibility to WCAG 2.2 AA, covering semantic HTML, keyboard operation, focus management, names and labels, color contrast, motion, forms, and automated plus manual testing. Use when building or reviewing UI components, forms, dialogs, or navigation.
---

# Accessibility Guide

Target WCAG 2.2 Level AA. Check each change with a keyboard and a screen reader, not only an automated scanner. Automated tools catch a fraction of defects.

## Semantics first
- Use the native element: `<button>` for actions, `<a href>` for navigation, `<label>` for form fields, `<h1>` to `<h6>` in order.
- Add ARIA only when no native element fits. A wrong `role` is worse than none.
- Lists are `<ul>` or `<ol>`. Tables use `<th scope>` for headers.

## Keyboard
- Every interactive control is reachable with Tab and operable with Enter or Space.
- No keyboard trap. Dialogs trap focus on purpose and return it to the trigger on close.
- Visible focus indicator. Do not remove `outline` without a replacement that meets contrast.

## Names
- Every control has an accessible name: visible text, `aria-label`, or a label element.
- Icon-only buttons need a label. Decorative images use `alt=""`; informative images describe the content, not the file.
- Link text makes sense out of context. Avoid "click here" or "read more" alone.

## Forms
- Each input has a visible label associated by `for`/`id` or by nesting.
- Errors are text next to the field, connected with `aria-describedby`, and announced: use `role="alert"` or an `aria-live` region for summary errors.
- Required fields are marked in text, not only by color or an asterisk alone.

## Color and motion
- Text contrast at least 4.5:1 for body text, 3:1 for large text and UI component boundaries.
- Do not convey meaning by color alone.
- Respect `prefers-reduced-motion`. Avoid autoplay motion longer than five seconds without a pause control.

## Focus management in SPAs
- After route change, move focus to the new page heading or a skip target.
- After a dialog closes, return focus to the element that opened it.

## Testing
- Automated: axe-core in component or end-to-end tests if the project has it. Report what it checked.
- Manual: tab through the page; use VoiceOver (macOS), NVDA or JAWS (Windows), or TalkBack (Android) on the changed flow.
- Zoom to 200 percent and to a narrow viewport. Content must not require horizontal scrolling for text.

## Checklist for a changed component
Keyboard operable. Focus visible. Name exposed. State announced (expanded, selected, invalid). Contrast checked. Works at 200 percent zoom.
