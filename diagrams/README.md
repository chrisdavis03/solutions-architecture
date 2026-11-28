# Diagrams

Keep the source and the export side by side.

- `.drawio` files are the **source**. Edit these.
- PNG/SVG files are **rendered exports**. Commit the one(s) you actually use, since Markdown viewers cannot open `.drawio`.

Generated render artifacts go in `diagrams/.render/`, which is gitignored — treat it as scratch, never link to it.

Link a diagram from a post with a relative path from the post's location:

```markdown
![Order flow](../diagrams/order-flow.png)
```

Name files for what they show (`order-flow.drawio`), not for when you drew them.
