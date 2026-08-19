# Personal record modules

These JSON arrays are structured support for short personal material. The current entries are explicitly marked verification demos; replace them with real records rather than creating a parallel content system. A module becomes public only after its file contains a record.

Suggested shapes are intentionally small and flexible:

```json
{
  "title": "Actual title",
  "status": "reading | finished | interested | abandoned",
  "date": "YYYY-MM-DD",
  "note": "Rijan's own optional note",
  "writing": "optional-published-writing-slug",
  "demo": false,
  "_source_note": "Source-only replacement guidance"
}
```

- `books.json`: `title`, optional `author`, `status`, `date`, `note`, `writing`
- `cinema.json`: `title`, optional `type`, `year`, `watched`, `note`, `writing`
- `chess.json`: `title`, optional `date`, `context`, `note`, `writing`
- `running.json`: `title`, optional `date`, `distance`, `location`, `note`, `writing`
- `travel.json`: `title`, optional `date`, `location`, `coordinates`, `note`, `writing`
- `technology.json`, `music.json`, and `food.json`: flexible short notes using the same base fields

Only `title` is required by the current builder. A `writing` value links the record to one published entry. `demo` and `_source_note` are source-only and are never rendered as record metadata. Keep opinions in `note` short; longer reflections belong in Writing. Do not add numeric ratings, analytics, or fields merely because another tracking service uses them.
