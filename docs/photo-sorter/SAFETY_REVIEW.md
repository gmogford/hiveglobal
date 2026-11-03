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
