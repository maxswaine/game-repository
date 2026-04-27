#a Frontend Changes Required

This document outlines backend changes that require corresponding updates in the frontend (`whats-that-game-app`). Changes are grouped by priority.

---

## 1. Upvoting — Breaking Changes

### What changed
The upvote endpoint is now a **toggle**. A single POST adds the upvote; calling it again removes it. The `remove` query parameter has been deleted. The `downvote` endpoint has also been removed entirely.

### Files to update

**`src/lib/api.ts`**

Replace:
```typescript
export async function upvoteGame(
  gameId: string,
  remove = false
): Promise<{ upvotes: number; downvotes: number }> {
  return request(
    `/games/${gameId}/upvote?remove=${remove}`,
    { method: "POST" },
    true
  );
}

export async function downvoteGame(
  gameId: string,
  remove: boolean
): Promise<{ upvotes: number; downvotes: number }> {
  return request(
    `/games/${gameId}/downvote?remove=${remove}`,
    { method: "POST" },
    true
  );
}
```

With:
```typescript
export async function upvoteGame(
  gameId: string
): Promise<{ upvotes: number }> {
  return request(
    `/games/${gameId}/upvote`,
    { method: "POST" },
    true
  );
}
```

**`src/components/GameDetail.tsx`**

- Remove any call to `downvoteGame`
- Update `handleUpvote` — no longer needs to pass `remove`. The toggle is handled by the backend. The `hasUpvoted` local state can stay as a UI hint but the backend is the source of truth on the count.
- Remove any downvote button/count from the UI

**`src/screens/GameDetailScreen.tsx`**

- Same as above — remove downvote logic and button
- Update `handleUpvote` to call `upvoteGame(gameId)` with no second argument

---

## 2. Themes Replaced by `game_setting` — Breaking Changes

### What changed
The `themes` field (an array of `{ theme_name: string }` objects) has been **removed entirely** from all game responses. It has been replaced by `game_setting`, which is a plain `string[]`.

The underlying database table has also been renamed:
- **Old table**: `game_themes` — stored objects with a `theme_name` enum column
- **New table**: `game_settings` — stores plain strings, no enum constraint

`game_setting` is free-form — users can type anything — but the backend provides a curated suggestion list via the metadata endpoint (see section 7 below).

### Files to update

**`src/lib/api.ts`** — `GameRead` interface

Remove:
```typescript
themes: { theme_name: string }[];
```

Add:
```typescript
game_setting: string[];
```

**`src/lib/mappers.ts`** — `mapGameReadToGame`

Remove the `themes` mapping line. Add:
```typescript
game_setting: g.game_setting,
```

**`src/types/game.ts`** — `Game` type

Remove:
```typescript
themes?: { theme_name: string }[];
```

Add:
```typescript
game_setting: string[];
```

**`src/components/GameDetail.tsx`** and **`src/screens/GameDetailScreen.tsx`**

- Remove any rendering of `themes` / `theme_name`
- Display `game_setting` as a flat list of strings instead

**Any form that creates or updates a game**

- Remove the `themes` field from the payload
- Add `game_setting: string[]` — an array of setting strings the user has selected/typed
- The metadata endpoint (section 7) provides the suggestion list for autocomplete

---

## 3. Game Response Shape — `downvotes` Removed  

### What changed
`downvotes` has been removed from all game API responses.

### Files to update

**`src/lib/api.ts`** — `GameRead` interface

Remove:
```typescript
downvotes: number;
```

**`src/lib/mappers.ts`** — `mapGameReadToGame`

Remove the `downvotes` line from the mapping function.

**`src/types/game.ts`**

Remove:
```typescript
downvotes?: number;
```

---

## 3. Auth — Cookie Support (Web)

### What changed
The `/auth/token` endpoint (username/password login) now sets an `httponly` cookie in addition to returning the token in the response body. This brings it in line with Google OAuth, which already set a cookie. The `/auth/refresh` endpoint reads from this cookie.

The bearer token flow **has not been removed** — the response body still returns `access_token`. No immediate change is required to keep login working. However, the following updates are needed to make refresh and cookie-based auth work properly on web.

### Files to update

**`src/lib/api.ts`** — `request()` function

Add `credentials: 'include'` to all fetch calls so the browser sends the httponly cookie automatically:

```typescript
const res = await fetch(`${API_BASE}${path}`, {
  ...options,
  headers,
  credentials: "include",   // ADD THIS
});
```

Also update the retry fetch inside the 401 handler:
```typescript
const retryRes = await fetch(`${API_BASE}${path}`, {
  ...options,
  headers,
  credentials: "include",   // ADD THIS
});
```

**`src/lib/api.ts`** — `tryRefreshToken()`

The refresh endpoint reads from a cookie — it does **not** accept a token in the request body. The current implementation sends a JSON body which will be ignored. Update it to rely on the cookie instead:

Replace:
```typescript
async function tryRefreshToken(): Promise<boolean> {
  const token = await getToken();
  if (!token) return false;
  try {
    const res = await fetch(`${API_BASE}/auth/refresh`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ access_token: token }),
    });
    if (!res.ok) return false;
    const data: TokenResponse = await res.json();
    await setToken(data.access_token);
    return true;
  } catch {
    return false;
  }
}
```

With:
```typescript
async function tryRefreshToken(): Promise<boolean> {
  try {
    const res = await fetch(`${API_BASE}/auth/refresh`, {
      method: "POST",
      credentials: "include",
    });
    if (!res.ok) return false;
    const data: TokenResponse = await res.json();
    await setToken(data.access_token);
    return true;
  } catch {
    return false;
  }
}
```

> **Note for React Native**: React Native's `fetch` does not handle cookies automatically. The bearer token path via AsyncStorage will continue to work for the mobile app. The `credentials: 'include'` change only takes effect in a browser context and is safe to add without breaking the native app.

---

## 4. OAuth Callback — Storage Inconsistency

### What changed
Nothing on the backend, but this was spotted during review.

### Issue
`src/pages/OAuthCallback.tsx` stores the token using `localStorage` directly, while `src/lib/api.ts` reads from `AsyncStorage`. These are different storage mechanisms — the token set by `OAuthCallback` will never be found by the `getToken()` function in `api.ts` on web.

### Fix
`OAuthCallback.tsx` should use the `setToken()` function from `api.ts` instead of writing to `localStorage` directly, so both paths write to the same place.

---

## 5. `/auth/verify` — Now Reliable

### What changed
This endpoint was previously broken at the backend (would crash at runtime). It is now fixed and returns:

```json
{
  "valid": true,
  "username": "string",
  "expires_at": "2026-04-19T12:00:00+00:00"
}
```

If the frontend has any token validity checks that were avoiding this endpoint due to unreliable behaviour, they can now use it.

---

## 6. `/users/me/complete-profile` — Auth Now Required

### What changed
This endpoint was previously broken at the backend (auth dependency was never injected). It is now fixed and properly requires an authenticated user.

### Impact
The frontend call in `src/lib/api.ts` (`completeProfile()`) already sends the bearer token via the `request()` wrapper with `auth: true`, so this should work without any changes. Verify the call passes `true` as the third argument to `request()`.

---

## 7. Metadata Endpoint — `game_themes` Renamed to `game_settings`

### What changed
The metadata endpoint response shape has changed. The `game_themes` key has been renamed to `game_settings` and now returns the full list of setting suggestions for the `game_setting` autocomplete field.

**Old response:**
```json
{
  "game_themes": ["Strategy", "Logic", "Bluffing", ...]
}
```

**New response:**
```json
{
  "game_settings": ["Date Night", "First Date", "Party", "House Party", "Dinner Party", "Game Night", "Pub / Bar", "Late Night", "Holiday", "Camping", "Road Trip", "Outdoor", "Classroom", "Icebreaker", "Work Appropriate", "Family Friendly", "Adults Only", "Drinking Optional", "Drinking Required", "Funny", "Silly", "Wholesome", "Romantic", "Spicy", "Awkward", "Dramatic", "Tense", "Argumentative", "Nostalgic", "Daring", "Dark", "Absurd", "Chill", "Casual", "Intense", "Chaotic", "Active", "Friendship Ruiner", "Quick", "Competitive", "Cooperative", "Team", "Solo Friendly", "Two Player", "Large Group", "Mixed Ages", "Creative", "Storytelling", "Conversation", "Roleplay"]
}
```

### Files to update

**`src/lib/api.ts`** — `GameMetadata` interface

Remove:
```typescript
game_themes: string[];
```

Add:
```typescript
game_settings: string[];
```

**Any component rendering the theme/setting suggestion list**

Update to read from `metadata.game_settings` instead of `metadata.game_themes` and use the values to drive the `game_setting` field autocomplete when creating or editing a game.
