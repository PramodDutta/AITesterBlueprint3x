# Verify a library's API by running it, before writing against it

## The problem

The spec for an MCP server said "pin FastMCP latest 2.x" and gave an example resource
signature returning `list[dict]`. Both were wrong for the version that a fresh install
actually gives you, and neither failure is visible by reading code.

## The approach

1. **Check what "latest" actually is** before trusting the word. `curl pypi.org/pypi/<pkg>/json`
   showed latest was 3.4.4, not 2.x. The brief's version guidance was stale.
2. **Install both candidate versions into throwaway venvs** in the scratchpad. Two `uv venv`
   calls, ~20 seconds.
3. **Introspect the real signatures** with `inspect.signature` rather than reading docs, which
   confirmed `@mcp.tool` / `@mcp.resource(uri)` / `@mcp.prompt` decorator shapes.
4. **Smoke-test every primitive shape end to end** with the library's own in-memory client.
   This is what caught the real breaks:
   - `list[dict]` returned from a resource works on 2.14.7, raises on 3.4.4
     (`TypeError: contents[0] must be ResourceContent, got dict`).
   - A bare `str` return works on both but **silently forces `mimeType: text/plain`**,
     overriding the `mime_type` declared on the decorator. Silent, so no error would ever
     have surfaced it.
   - Fix: return `[ResourceContent(payload, mime_type="application/json")]`. Note the outer
     list. Returning a bare `ResourceContent` also raises.
5. **Test the error surface too**, not just the happy path. Raising `ToolError` /
   `ResourceError` / `PromptError` sends a clean message to the client while a traceback goes
   to stderr only, which is what "never return a bare stack trace" actually requires.
6. Only then write the real file, and re-run the same harness against it (31 assertions).

## The judgment calls

- **Did not trust the example signature in the brief**, even though it came from the person
  who knows the project. Example code in a prompt is a sketch, not a contract.
- **Did not silence FastMCP's stderr tracebacks on expected errors**, though they look alarming
  in a demo. Muting that logger would also hide real bugs. The client-visible message is
  already clean, which is the part the requirement was actually about.
- **Did not golf the file down to the stated ~250 lines** by deleting functional code. Landed
  at 292 physical / 245 non-blank and reported the number honestly instead.
- **Did not kill the Inspector already running on port 6277.** It belonged to a different
  server the user had started. Used `CLIENT_PORT` / `SERVER_PORT` to run alongside it.
- **Did not fix the `list[dict]` break by pinning 2.14.7**, the version where the broken code
  happens to work. A student running `uv add fastmcp` gets 3.x and would hit the error anyway.
  Fix the code, not the pin.

## The reusable rule

**When a task says "use library X", install X and run a throwaway smoke test of every API
shape you plan to use before writing the real file. Version guidance in a prompt is a claim to
verify, not a fact.** The bugs that matter here are the silent ones: an API that "works" but
quietly returns the wrong metadata will never announce itself, so assert on the output values,
not just on the absence of an exception.
