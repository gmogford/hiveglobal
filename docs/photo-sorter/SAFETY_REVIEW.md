# Photo Sorter: step-by-step safety review of the original prompt

**Short answer:** do not point this tool, or any tool that moves files, at your
Photos/iPhoto library. Export the photos to an ordinary folder first and sort that folder.
The original prompt says the same ("Never pick your Photos Library folder").
The hardened prompt in `PROMPT.md` makes the app enforce it.

## Why the Photos library is off-limits

`Photos Library.photoslibrary` (and older `iPhoto Library`) is a macOS *package*: a
folder containing a SQLite database (`database/Photos.sqlite`) plus `originals/`,
`resources/` and other folders. The database records the exact path of every file. If any
tool moves, renames or adds files inside it, Photos loses track of them, and the
library can need a repair (⌥⌘ at launch) or lose edits, albums and metadata. With iCloud
Photos on, those changes can sync. The library's top level also holds almost no image files
(they're in subfolders), so even a "read only top-level files" sorter would find nothing
useful there.

## Step-by-step check of the original prompt

| # | Original step | Problem found | Fix in `PROMPT.md` |
|---|---|---|---|
| 1 | "One index.html, no server, no paid APIs" | Nothing stops the generated code from loading a CDN or sending data. | CSP meta tag with `connect-src 'none'`, no external requests. |
| 2 | Title shows folder name | If inserted with `innerHTML`, a crafted folder name could inject HTML. | Use `textContent`. |
| 3 | Animation | Hundreds of full-size images freeze or crash the tab. | Small bitmap thumbnails, cap the number of sprites, revoke URLs. The animation never touches files. |
| 4 | Categories from colour/shape | Fine. Wrong guesses are harmless because nothing is deleted. HEIC won't decode in Chrome. | HEIC fallback, per-file try/catch. |
| 5 | Duplicates via SHA-256 | Hashing every large video loads it fully into memory. The prompt doesn't say which copy is kept. | Group by size first, size cap, defined "keeper". |
| 6 | `showDirectoryPicker` readwrite | Asks for write access before you've seen anything. | Read first, ask for write only at confirm. |
| 7 | No folder guard | Nothing prevents picking the Photos library or `~/Pictures`. | Hard refusal on library packages and their internal structure, warning on broad folders. |
| 8 | "Organise N files?" Move/Copy | You can't see what will happen. | Full preview list, Copy is the default. |
| 9 | "Never overwrite" | **Real trap:** `getFileHandle(name, {create:true})` + `createWritable()` silently truncates an existing file of the same name. | Explicit existence check, plus `(1)`, `(2)` naming. |
| 10 | "Never delete" + Move | Move is often implemented as copy then delete original. A failed copy plus a delete loses the photo. | Use `FileSystemFileHandle.move()` only. Disable Move if it's unavailable. Never `removeEntry` a file the app didn't create. |
| 11 | "Add Undo" | Undo held only in memory is lost on refresh or crash. Undoing a copy means deleting, so the app has to be sure it deletes only its own copy. | JSON log written to the folder before acting. Undo deletes only its own copies, and only after verifying the original. |
| 12 | Errors | Not specified. Partial runs leave an unknown state. | Stop on error, report, log stays accurate, Undo still works. |
| 13 | "Test on a throwaway folder" | Good advice, but not enforced. | Test checklist uses a throwaway folder, including a test that it refuses a `.photoslibrary`. |
| 14 | "📱 iPhone" | `showDirectoryPicker` doesn't exist in Safari or on iPhone/iPad. Real sorting is desktop Chrome/Edge only. | Feature detection with a clear message. Demo still works. |

## Residual risks (even with the hardened prompt)

- The code is AI-generated. Read the "safety rules" comment block, and test on a throwaway
  folder before using it on real exports.
- Keep your Photos library / iCloud as the master copy. The sorted export folder is a
  working copy, so even a worst-case bug can't lose a photo.
- Category accuracy is a rough heuristic. Expect to drag some files by hand afterwards.

## Premortem: "It's six months later and the Photo Sorter caused a disaster. Why?"

Ranked by likelihood × damage. **Fixed** means `PROMPT.md` was updated to cover it.

| # | Failure story | Likelihood | Damage | Status |
|---|---|---|---|---|
| 1 | The generated code quietly skipped a safety rule (long prompt, long file, model ran out of room), and nobody checked. | High | High | **Fixed:** the prompt now asks for a rule-to-function self-check table, an audit of every `removeEntry`/`createWritable`/`move` call, and a full file rather than a truncated one. You still have to read the table. |
| 2 | You picked the Photos library or `~/Pictures` anyway, and the folder guard had a bug or didn't recognise the layout. | Medium | Severe | Partly fixed. The only real defence is not picking it. Export to `~/Desktop/to-sort` and keep a **Time Machine backup** (step 0 added). |
| 3 | Undo cleanup called `removeEntry(dir, {recursive:true})` and wiped a category folder that held your own files. | Low–Med | Severe | **Fixed:** `recursive` is banned, and only folders the app created can be removed. |
| 4 | Undo ran after you'd tidied things by hand: it moved the wrong files back or failed halfway. | Medium | Medium | **Fixed:** Undo checks each file's logged path and size and skips mismatches. |
| 5 | Name was free when the plan was built but taken when the operation ran (second run, Finder open), so the file got overwritten. | Low | High | **Fixed:** the name is re-checked right before each operation. |
| 6 | Copy filled the disk on a big video folder, leaving half-written files. | Medium | Low | **Fixed:** the dialog shows the GB total; the size check already removes half-written copies. |
| 7 | "It froze." Scanning 5,000 photos took minutes with no feedback, so you force-quit mid-run. | High | Low | **Fixed:** visible scan phase with progress and Cancel. Stop/Undo already survive a partial run via the log. |
| 8 | Finder dates all became "today" after Copy, and date-sorted views were ruined. | High | Low | **Fixed:** explained in the dialog. EXIF dates inside the photo are unaffected, and Move keeps dates. |
| 9 | The duplicate "keeper" was arbitrary, because every exported file has the same export timestamp. | High | Low | **Fixed:** the keeper is chosen by filename (no " (1)"/"copy" suffix). |
| 10 | JPEG export lost Live Photo motion and HEIC quality, and you later deleted the library thinking the export was the archive. | Low | Severe | Not fixed in code. Treat the export as a **working copy** and never as a replacement for the library/iCloud. |
| 11 | Move was unavailable in your Chrome version and a "helpful" rewrite emulated it with copy + delete. | Low | High | Covered: the rule bans emulation, and the self-check table must list every `move`/`removeEntry` call. |
| 12 | Categories were poor (exported screenshots are JPEG, not PNG; colour heuristics are crude), so you gave up. | High | None | Accepted. Nothing is lost, and it's a fun visual sorter, not a curator. |

### Tripwires before trusting it with real exports
- Read the SAFETY SELF-CHECK table, then search the HTML for `removeEntry`, `recursive`,
  `createWritable` and `fetch`. You should see no `recursive` and no `fetch`.
- Run the full throwaway-folder checklist, including refresh-then-undo and the
  `.photoslibrary` refusal.
- Confirm a backup exists before the first real run.
