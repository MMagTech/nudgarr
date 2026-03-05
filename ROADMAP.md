# Roadmap

Planned features for upcoming releases. Nothing here is guaranteed — priorities may shift based on feedback and testing.

---

## v2.6.0

**Per-instance enable/disable**
Each instance card will have an Enable/Disable toggle sitting inline with the Edit and Delete buttons. Disabled instances are skipped entirely during sweeps and health checks — the dot goes grey and the card dims. Re-enabling triggers an immediate health ping. The toggle updates live without requiring a save.

**Per-arr sample mode**
Sample mode will split into `radarr_sample_mode` and `sonarr_sample_mode` — independently configurable per app. Useful when you want Oldest Added for movies (working through a backlog) and Newest Added for shows (keeping up with recent additions). Cooldown remains global. The Newest Added warning will check each mode independently.

**Library Added column in History**
A Library Added column showing when each item was added to your Radarr or Sonarr library. Makes sample mode behaviour immediately verifiable — you can see the added date right next to the last searched date without leaving the app. Column order: Title → Instance → Type → Library Added → Last Searched → Eligible Again.

**Search count in History**
A count showing how many times Nudgarr has searched each item. Items with a high count that still haven't imported may indicate an indexer problem or a release that doesn't exist yet.

---

## v2.7.0

**Sweep tab**
A dedicated Sweep tab between Instances and History. One card per instance in the same style as the Instances tab — showing last run time for that instance independently (disabled instances retain their last run time), eligible/skipped/searched counts from the last sweep, and the sample mode in use. Reads from existing sweep summary data — no new backend storage needed.

**Exclusion list**
Exclude specific titles from ever being searched. The `⊘` icon appears on History rows on hover — clicking it adds the item to a separate `nudgarr-exclusions.json` file. A filter pill appears in the History instance filter area only when exclusions exist. Selecting it shows excluded items only, where the icon becomes an Unexclude action for that row. Excluded items remain visible in History as a log of past searches.

---

Items not on the roadmap by design: additional arr support (Readarr, Lidarr) — the codebase is open source and welcomes forks for this. Webhook trigger endpoint — Nudgarr is intentionally one-directional. Dashboard charts — keeps the single-file approach lean.
