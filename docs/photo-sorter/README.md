# Photo Sorter

`index.html` is a single offline file built from `PROMPT.md`. Open it in **desktop Chrome or Edge**.
Safari, Firefox and iPhone/iPad can only run the Demo.

Before using it on real photos, read `SAFETY_REVIEW.md` and follow
"Using it with iPhone/Mac photos" in `PROMPT.md`: back up first, export to a normal folder, and never pick the Photos Library.

## Safety self-check

| Rule (PROMPT.md, REAL SORTING) | Implemented in |
|---|---|
| 1. Read-only picker, write access only on Copy/Move/Undo | `chooseFolder`, `ensureWritePermission` |
| 1. Only files directly in the folder | `listTopLevel` (lists subfolders by name only, never opens them) |
| 1. Ignore hidden/system/log files | `isIgnored` |
| 2. Refuse library packages, library insides, broad folders | `checkFolderSafety` (runs before any file is read) |
| 3. Full plan, Copy default, size + date explanation | `openPlanDialog` |
| 4. Free-name check right before every write, `(1)` naming | `nameTaken`, `freeName` |
| 4. Track which category folders were created | `ensureFolder` |
| 4. Stream copy + size verification | `copyInto` |
| 4. Real `move()` only, button disabled otherwise | `SUPPORTS_MOVE`, `runOrganise` |
| 4. One at a time, Stop | `runOrganise`, `progressDialog` |
| 5. Log written before first op and kept updated | `runOrganise`, `makeLogWriter` |
| 5. Undo: checks before every step, skips mismatches | `undoRun` |
| 5. Offer to undo a previous run after reopening the folder | `detectPreviousRun`, `sanitiseLog` |
| 6. Stop on error, name the file, keep the log | `runOrganise` (catch block) |

### Every call that can change or remove data

| Line | Call | Why it's safe |
|---|---|---|
| 888 | `createWritable()` in `copyInto` | The file was created a moment earlier by this run and confirmed 0 bytes; otherwise the run stops. |
| 891, 896 | `removeEntry(newName)` in `copyInto` | Only removes this run's own failed or wrong-size copy. The original is never touched. |
| 905 | `createWritable()` in `makeLogWriter` | Rewrites only the log file this run created under a free name. |
| 968 | `move()` in `runOrganise` | Destination name was checked free immediately before. Source size/date re-checked against the scan. |
| 1022 | `move()` in `undoRun` | Moves a logged file back to a free name in the chosen folder. Only runs if the file's size matches the log. |
| 1033 | `removeEntry()` in `undoRun` | Removes a logged copy only if it lives in one of the app's category folders, was written after the run started, its size matches, **and** the original is still present with the same size. |
| 1044 | `removeEntry(folder)` in `undoRun` | Only category folders this app created, only after checking they're empty. Called without options, so a non-empty folder can't be deleted. |
| 1053 | `createWritable()` in `undoRun` | Writes a new "undo" marker file under a free name. The old log is never rewritten. |

The words `recursive`, `fetch` and `innerHTML` do not appear in `index.html`. The CSP blocks all network requests.

## Automated test results (headless Chromium, sandboxed browser file system)

All of these pass:
- Demo: 151 files, every category filled, animation runs ≈5.6 s, counters match the total, R replays, no dialog and no writes.
- Scan: 9 top-level files found; `.DS_Store` and the nested subfolder are ignored; one duplicate found.
- Classification: golden, sky, night, portrait, PNG screenshot, undecodable `.heic` → Everyday (no preview), `.txt` → Docs, `.webm` → video.
- Copy: an existing `Golden hour/IMG_A.jpg` is **not** overwritten (the copy becomes `IMG_A (1).jpg`). All originals are intact. The log lists 9 ops. The pre-existing folder is not marked as created.
- Reload, then undo: the previous run is offered, and undo restores the exact original tree.
- Move, then delete one sorted file by hand, then undo: the deleted file is reported as skipped. Everything else is moved back and the empty folders are removed.
- Stop halfway, then undo: only the 120 originals remain.
- Refuses `Photos Library.photoslibrary`, a folder containing `originals/`, and `Pictures`.
- No horizontal scroll at 390 px. No console errors. Zero external network requests.

## Manual test checklist (use a THROWAWAY folder, never your real photos)

Make `~/Desktop/sorter-test` with: 5–10 JPEGs exported from Photos, one exact duplicate (Finder → Duplicate),
one `.HEIC`, one short and one long `.mov`, one `.txt`. Also make a `Golden hour` subfolder containing any file renamed to match one of your JPEGs.

1. **Copy:** Choose folder → Space → check the plan list → Copy. The originals are still in the folder, and copies are in the subfolders.
2. **Name collision:** the matching file inside `Golden hour` is untouched, and the copy is named `… (1).jpg`.
3. **Duplicates:** the "copy" file went to `Duplicates`, and the original went to a category folder.
4. **HEIC / video / txt:** HEIC → Everyday shots, `.mov` files → the right length folder, `.txt` → Docs & other.
5. **Undo after copy:** Undo → the subfolders it created are gone, and `Golden hour` and its file are still there.
6. **Move + undo:** run again, choose Move, check the root is empty, then Undo. Everything is back.
7. **Refresh, then undo:** Copy, reload the tab, choose the same folder → "Undo previous run" → everything is back.
8. **Undo after a manual delete:** Move, delete one sorted file in Finder, Undo → it's listed as skipped, and the rest come back.
9. **Stop halfway:** use a folder with a few hundred files, press Stop during the copy, then Undo.
10. **Refusal:** try to pick `~/Pictures/Photos Library.photoslibrary` (in the picker, right-click → Show Package Contents if needed) and `~/Pictures`. Both must be refused.
