# Android app

The TV Tracker Android app connects to the same server as the website (`tvtracker.melamoud.com`) and uses your Trakt login.

## What it does

- **My Shows / My Movies** — the same list filters as the web (status, Lists…, Upcoming / Theater / Streaming, title search), each as a compact dropdown with checkmarks. **List** vs **Newest aired** is the same server sort as the website (pins on top; movies by release date; shows by latest episode air date). Switching that menu reloads from the server. Cards show **Progress** and **Watch**; pin, set lists, rate, and favorite are in the ⋮ menu.
- **Search** — find titles on Trakt and add them to your lists. **Type** and **Filters** are compact menus (defaults hide already-watched and already-listed titles). Filters also include **Year** (`2018` or `2015-2020`) and multi-select **Genres**; a title is still required.
- **Alerts** — the same in-app alerts as the website, including **Found on** and streaming lines. Episode/season cards have **Progress**. After you mark episodes watched on Progress, Alerts reloads when you go back (matching alerts are marked read on the server immediately).
- **Progress** — mark episodes or a whole season watched / unwatched. Writes to Trakt.

Latest movies/shows and Recommended screens are website-only for now.

## Refresh

Pull down on any list, or tap the refresh icon. That reloads from the TV Tracker server (the same cache the website uses). It does **not** force a Trakt pull. Lists also reload when you return to them (including after Progress).

## Login

There is no local password. Tap **Login with TraktTV**, authorize in the browser, then the app opens again to finish. If the browser stays open, tap **Open TV Tracker**.

Stay signed in until you tap **Log out**.
