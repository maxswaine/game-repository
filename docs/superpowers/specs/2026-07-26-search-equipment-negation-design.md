# Search: per-item equipment negation

## Problem

`POST /games/search/` embeds the query and ranks public games by cosine similarity, with one
existing hard filter: `_wants_no_equipment` catches blanket phrases ("no equipment", "hands only",
etc.) and restricts results to games whose only equipment is `"No Equipment"`.

It does not handle negation of a *specific* item. A query like "a game for 5 friends in a bar with
no cards" still ranks card games highly, because the embedding model weights the token "cards"
regardless of the "no" in front of it. The user wants card games excluded outright, not
down-ranked.

## Approach

Extend `_apply_hard_filters` in `src/api/search.py` with a second, narrower hard filter:

1. If the query contains a blanket no-equipment phrase, keep current behavior unchanged (short
   circuits before the new logic — a blanket phrase already implies every specific item is out).
2. Otherwise, scan the query for negation phrases referencing specific equipment nouns ("no
   cards", "without dice", "no cards and no dice"), resolve each noun (and 2-word window, to catch
   "playing cards") against a keyword index derived from `GameEquipmentEnum`, and hard-exclude any
   game that has one of the matched equipment items.

This stays a hard filter — consistent with the existing no-equipment behavior — not a scoring
penalty. It runs independently of the embedding step, so it composes with search relevance
unchanged.

## Components

### Keyword index (`_equipment_keyword_index`, module-level, built once at import)

Built once from `GameEquipmentEnum` by tokenizing each enum value:

- Lowercase, split on whitespace and hyphens.
- Drop stopwords (`a`, `an`, `of`, `the`, `and`, `to`, `for`).
- Fold naive plurals (strip trailing `s` when indexing and when matching a query word), so query
  "card" matches enum word "cards" and vice versa.
- Map each surviving word -> `set[GameEquipmentEnum]` of every enum member whose value contains
  that word.

No hand-curated category lists. Coverage grows automatically as new `GameEquipmentEnum` members
are added, since the index rebuilds from the enum at import time.

Known collision to accept as-is: "index cards" and "standard deck of cards" both index under
"card" — this is correct, both are card-shaped equipment a "no cards" query should exclude.

### Negation detection (`_excluded_equipment_from_negations(query: str) -> set[GameEquipmentEnum]`)

Regex over the lowercased query, using `findall` (not a single match) so multiple negations in one
query all contribute:

```
(?:no|without|never|don'?t (?:want|need)(?: any)?|not any) ([a-z]+(?: [a-z]+)?)
```

For each captured phrase: try the full 2-word phrase against the index first (handles "playing
cards"), then fall back to each individual word. Union all matched `GameEquipmentEnum` sets across
every negation found in the query.

### Filter integration

```python
def _apply_hard_filters(games: list, query: str) -> list:
    if _wants_no_equipment(query):
        return [
            g for g in games
            if all(e.equipment_name == "No Equipment" for e in g.equipment_items)
        ]
    excluded = _excluded_equipment_from_negations(query)
    if excluded:
        games = [
            g for g in games
            if not any(e.equipment_name in excluded for e in g.equipment_items)
        ]
    return games
```

`e.equipment_name` is stored as the enum's string value, so membership checks compare against
`GameEquipmentEnum` values directly (or `.value` as needed to match existing storage format).

## Error handling

No new failure modes: this is pure string/set logic with no I/O. Malformed or nonsensical
negations (e.g. "no fun") simply match nothing in the index and are a no-op, same as query text
today that doesn't match a hard filter.

## Testing

New `tests/api/search/` directory (search currently has no dedicated test dir), following the
existing per-router convention:

- `tests/api/search/__init__.py`
- `tests/api/search/test_search.py`, using `tests/api/games/helper.py` builders
  (`create_public_game`, `create_user`, `get_user_token`) and `tests/utils.py` payload builders.

Cases:

1. "no cards" excludes games whose equipment includes any card-category `GameEquipmentEnum`
   member (`standard_deck`, `jokers`, `multiple_decks`, `tarot_deck`, `improvised_cards`,
   `less_than_a_deck`, `uno_deck`), keeps games without card equipment.
2. "without dice" excludes dice-category equipment games.
3. "no cards and no dice" excludes games matching either category (union behavior).
4. False-positive guard: a query that mentions "cards" without a negation trigger (e.g. "a card
   game for 4 players") is unaffected — ranks normally via embedding, no hard exclusion.
5. Blanket "no equipment" phrase still takes the existing priority path and is unaffected by the
   new per-item logic.
6. "playing cards" (2-word phrase) resolves via the bigram lookup, not just the fallback single
   words.

## Out of scope

- Game type / setting / difficulty negation (e.g. "not a trivia game") — explicitly deferred,
  equipment-only for this change.
- Any scoring-based (soft) treatment of negation — this is a hard filter only, matching the
  existing no-equipment precedent.
