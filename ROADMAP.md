# Roadmap

Planned features for upcoming releases. Nothing here is guaranteed — priorities may shift based on feedback and testing.

---

## v2.7.0

**Sweep tab**
A dedicated Sweep tab between Instances and History. One card per instance in the same style as the Instances tab — showing last run time for that instance independently (disabled instances retain their last run time), eligible/skipped/searched counts from the last sweep, and the sample mode in use. Reads from existing sweep summary data — no new backend storage needed.

**Exclusion list**
Exclude specific titles from ever being searched. The ⊘ icon appears on History rows on hover — clicking it adds the item to a separate `nudgarr-exclusions.json` file. A filter pill appears in the History instance filter area only when exclusions exist. Selecting it shows excluded items only, where the icon becomes an Unexclude action for that row. Excluded items remain visible in History as a log of past searches.

---

Items not on the roadmap by design: additional arr support (Readarr, Lidarr) — the codebase is open source and welcomes forks for this. Webhook trigger endpoint — Nudgarr is intentionally one-directional. Dashboard charts — keeps the single-file approach lean.
