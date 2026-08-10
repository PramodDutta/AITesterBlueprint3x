# Document only what exists, and verify the facts you document

**Problem:** A "/go"-style task said *update the README for new work and push*. The README had a visible gap (chapter 08 jumped to chapter 10), and the missing chapter's only file was a 0-byte placeholder.

## The approach

1. **Detect before writing.** `git status`, `git log`, `git show --stat` on the last commit. Working tree was clean, one unpushed commit. The commit's "new" files were mostly binary assets and two commented-out stub labs, so there was nothing substantive to document there.
2. **Diff the docs against the filesystem, not against the commit.** Grepped the README for every chapter directory. `chapter_09_MCP_Basics` had **zero** references. Then checked the chapter itself: `wc -c` on its only file returned `0`.
3. **Stop and ask.** Writing a rich README section about a chapter whose content file is empty is fabrication. Surfaced the finding and offered three scopes: author the chapter content and document it, skip chapter 09 entirely, or add a "(in progress)" stub. User picked "author it".
4. **Verify the domain facts against the live source.** The chapter was about MCP. Fetched the current spec instead of writing from memory. Revision `2026-07-28` turned out to be **stateless** with a `server/discover` probe. Memory said session-based with an `initialize` handshake. Both eras exist in the wild, so the note documents the split rather than picking one.
5. **Sync every insertion point, then verify mechanically.** The README repeats structure in five places (curriculum mindmap, directory tree, chapter body, task lookup list, requirements list). Updated all five, then checked code-fence parity with a script and read the mindmap region back to confirm indentation matched its siblings.

## Judgment calls

- **Did not write the README section from the chapter title alone.** "MCP Basics" is enough to bluff a plausible section. That section would have described content that did not exist, and nobody would have caught it until a reader opened the empty file.
- **Did not treat "go go go" as blanket authority to invent content.** The command authorized commit-and-push. Authoring an entire chapter of a paid course is a different act, and it is the author's voice. Asked; cost one turn.
- **Did not write MCP facts from training data.** The protocol had changed in exactly the area the chapter teaches (lifecycle and capability negotiation). Three fetches were cheaper than shipping confidently wrong teaching material.
- **Did not update the Chapter History section.** It was already stale for chapters 07, 08, 10, and 11. Adding only a chapter 09 line would imply the rest was current. Left it and reported it.
- **Did not use `git add -A`.** Staged the two intended paths so unrelated working-tree files could not ride along.

## The reusable rule

**Before writing documentation about a thing, open the thing.** If it is empty, missing, or contradicts how it was described, surface that instead of writing prose around it. Docs describing an artifact that does not exist are worse than a visible gap, because the gap is honest.

Corollary: when the doc teaches a spec, protocol, or library API, fetch the current version first. The areas most worth teaching are the areas most likely to have changed since training. (See also `2026-07-25-verify-library-api-before-writing-against-it.md`.)
