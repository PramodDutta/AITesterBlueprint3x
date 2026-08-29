# Playwright verification harness

The generated `.spec.ts` files are checked here, not executed against a live
site. `scripts/check_playwright.py` copies the specs from a run's artifact
directory into `tests/`, then runs:

- `npx tsc --noEmit` - does it compile as strict TypeScript?
- `npx playwright test --list` - does Playwright collect the tests?

Neither command opens a browser or contacts a server.

```bash
cd tools/playwright-check && npm install
python scripts/check_playwright.py outputs/RUN-YYYYMMDD-HHMMSS
```
