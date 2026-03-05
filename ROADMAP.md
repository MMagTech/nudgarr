# Roadmap

Planned features for upcoming releases. Nothing here is guaranteed — priorities may shift based on feedback and testing.

---

## v2.7.0

**Sweep tab**
A dedicated Sweep tab between Instances and History. One card per instance in the same style as the Instances tab — showing last run time for that instance independently (disabled instances retain their last run time), eligible/skipped/searched counts from the last sweep, and the sample mode in use. Reads from existing sweep summary data — no new backend storage needed.

**Exclusion list**
Exclude specific titles from ever being searched. The ⊘ icon appears on History rows on hover — clicking it adds the item to a separate `nudgarr-exclusions.json` file. A filter pill appears in the History instance filter area only when exclusions exist. Selecting it shows excluded items only, where the icon becomes an Unexclude action for that row. Excluded items remain visible in History as a log of past searches.

**Favicon**
A favicon so Nudgarr has a recognisable identity in your browser tabs and bookmarks bar.

---

Items not on the roadmap by design: additional arr support (Readarr, Lidarr) — the codebase is open source and welcomes forks for this. Webhook trigger endpoint — Nudgarr is intentionally one-directional. Dashboard charts — keeps the single-file approach lean.

---

## v3.0 — Maybe, someday

A proper mobile layout — same backend, same logic, just a UI built for smaller screens. Realistically, vibe coded projects don't exactly have a track record of setting the world on fire, but if this one somehow finds its audience, a mobile UI would be the natural next step.
