# Photo Sorter: build prompt (safety-hardened)

Paste everything inside the fenced block into Claude (or another coding assistant).
The safety review that explains each change is in `SAFETY_REVIEW.md` next to this file.

```text
Build me a "Photo Sorter": ONE self-contained index.html file that I open in desktop
Chrome (macOS). No server, no build step, no paid APIs, no external network requests
of any kind: no CDNs, fonts, analytics or uploads. My photos must never leave my machine.
Add this CSP meta tag and make sure everything still works with it:
<meta http-equiv="Content-Security-Policy" content="default-src 'none'; img-src blob: data:; media-src blob:; style-src 'unsafe-inline'; script-src 'unsafe-inline'; connect-src 'none'">

LOOK
- Minimal light app window. Title "Sorting my <folder name> folder" with the folder name
  in italic serif. Set the name with textContent, never innerHTML.
- Stats row: Total files, Photos, Videos, Duplicates.
- Left column: Photos category cards. Middle: the pile. Right: Videos + Cleanup cards.
- Toolbar: Choose folder, Demo, Replay, Sort, Undo (disabled until something can be undone).

ANIMATION
- Thumbnails form a slowly spinning circular pile: sunflower (golden-angle) spiral,
  slightly tilted, white borders like tiny polaroids.
- Press Space (or Sort) and each one flies in a curved arc into its category card,
  slow then faster, card counters ticking up. Total 5–8 seconds whatever the file count.
- requestAnimationFrame + CSS transforms only. Show at most ~300 thumbnails in the pile;
  if there are more, the remaining ones count up on the cards without their own sprite.
- Make thumbnails small (about 160px on the long side) using createImageBitmap /
  canvas, and revoke every object URL when it's no longer needed.
- The animation is ONLY a visualisation. It must never touch the file system.

CATEGORIES (heuristics; a wrong guess is fine because nothing is ever deleted)
- Photos (from each thumbnail's average colour, brightness and shape):
  Screenshots (PNG, or dimensions that match a common phone/desktop screen),
  Night & moody (dark), Golden hour (warm orange/amber), Sky & sea (blue-dominant),
  Portrait shots (taller than wide), Everyday shots (everything else).
- Videos (from <video> loadedmetadata duration): Quick clips <10s, B-roll 10–60s,
  Long takes 60s+. If Chrome can't read a video's duration, put it in B-roll and
  mark it "unknown length" in the plan.
- Duplicates: identical bytes. Group files by size first and only SHA-256
  (crypto.subtle.digest) files that share a size. Skip hashing files over 1 GB
  and say so. In each duplicate group, the copy with the oldest lastModified (tie: shortest
  name) is the "keeper" and is sorted normally; the others go to the Duplicates folder.
- Docs & other: anything that isn't a decodable image or video.
- HEIC/HEIF that Chrome can't decode: classify by extension as Everyday shots and show
  a grey placeholder thumbnail. Never crash on a file that won't decode; wrap each one in
  try/catch and keep going.

REAL SORTING: the safety rules below are mandatory
1. Folder access
   - Use window.showDirectoryPicker({ mode: 'read' }) first. Request 'readwrite'
     (handle.requestPermission) only when I confirm the organise step.
   - Only look at files DIRECTLY in that folder. Never recurse into subfolders.
   - Ignore hidden/system files: names starting with "." , ".DS_Store", "Thumbs.db",
     "desktop.ini", and the app's own log file.
2. Refuse dangerous folders. Before reading anything, stop with a clear message if:
   - the folder name ends in ".photoslibrary", ".aplibrary" or ".migratedphotolibrary", or
   - the folder contains a subfolder named "database", "originals", "resources",
     "Masters" or "private", or a file named "Photos.sqlite" (the inside of a Photos/iPhoto
     library), or
   - the folder name is "Pictures", "Desktop", "Documents", "Downloads" or the home folder
     (show a warning: "Pick a dedicated folder of exported photos instead"; allow
     Demo only).
3. Plan before acting
   - After the animation, show a dialog: "Organise N files?" with a scrollable preview
     list of every "file → destination folder" and buttons Copy (default, pre-selected),
     Move, and Cancel. Explain Move in one line: "Files are moved into subfolders
     here; Undo puts them back."
4. Never delete, never overwrite
   - Destination subfolders are created inside the chosen folder with
     getDirectoryHandle(name, { create: true }).
   - Before writing, check whether a file with that name already exists in the
     destination (getFileHandle without create, catch NotFoundError). If it exists,
     pick a free name: "IMG_0001 (1).jpg", "IMG_0001 (2).jpg", … Never call createWritable
     on a file that already existed (createWritable truncates = overwrite).
   - Copy: stream the source into the new file (file.stream().pipeTo(writable)), then
     re-read the new file and confirm its size matches. If it doesn't match, delete only
     that half-written copy and report the error.
   - Move: use FileSystemFileHandle.move(destDirHandle, newName) only. If move() is not
     available in this browser, disable the Move button and explain why. Do NOT
     emulate move with copy + delete of the original.
   - The app must never call removeEntry() on any file it did not create during this run.
   - Process files one at a time, with a progress bar and a Stop button. Stopping
     keeps whatever is already done and still allows Undo.
5. Log + Undo
   - Before the first operation, write "photo-sorter-log-<timestamp>.json" into the chosen
     folder and append each completed operation to it (op type, original name, new path,
     size). Keep it in memory too.
   - Undo reverses the last run in reverse order:
       moved files → move() back to the original folder under the original name (if that
       name is taken, use a free "(n)" name and say so);
       copied files → removeEntry() ONLY on the copy the app created, and ONLY after
       confirming the original still exists with the same size.
     Then remove category subfolders that are now empty (and only if empty).
   - On "Choose folder", if a photo-sorter log exists, offer "Undo previous run".
6. Errors: if any operation fails (permission revoked, disk full, name too long), stop,
   show which file failed, and leave everything already done listed in the log.

EXTRAS
- Demo button: generate ~120 fake "photos" (canvas gradients in the category colours,
  a few portrait-shaped, some fake PNG "screenshots") and ~20 fake videos with fake
  durations, plus a few duplicates. Demo mode never requests a folder and never writes.
- Keyboard: Space = sort, R = replay (re-form the pile and play again; animation only).
  Ignore the shortcuts while a dialog is open or focus is in an input.
- If showDirectoryPicker is missing (Safari, Firefox, iPhone/iPad), show
  "Real sorting needs desktop Chrome or Edge. Demo still works."

DELIVERABLE
- One index.html, commented, with the safety rules above as a comment block at the top.
- At the end, give me a short manual test checklist that uses a THROWAWAY test folder
  only (never my real photos) and covers: copy, move, undo after copy, undo after move, name
  collision, duplicates, a HEIC file, a video, a .txt file, and picking a
  .photoslibrary folder (it must refuse).
```

## Using it with iPhone/Mac photos (do this every time)

1. In the Mac Photos app, select the photos and choose **File → Export → Export N Photos…**,
   set Photo Kind to **JPEG**, and export into a new folder, e.g. `~/Desktop/to-sort`.
   (Wait for iCloud originals to download if "Optimize Mac Storage" is on.)
2. Do the first run on a **copy** of that folder, or on a few test images.
3. Open `index.html` in Chrome, click **Choose folder**, pick the export folder.
4. **Never** pick `Photos Library.photoslibrary`, the `Pictures` folder, or anything inside them.
   The app refuses these, but don't rely on that.
5. Choose **Copy** the first time. Use **Move** only after checking the result.
