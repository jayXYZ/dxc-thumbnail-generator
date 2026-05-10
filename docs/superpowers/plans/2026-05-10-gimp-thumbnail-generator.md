# GIMP Thumbnail Generator Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build a Python CLI that fills `thumbnail-template.xcf` with tournament text and Scryfall original-art crops, then exports a PNG thumbnail.

**Architecture:** Keep reusable logic in importable helper functions and keep GIMP-specific code at the edge. Use Scryfall fuzzy lookup first, then search by resolved `oracle_id` with `not:reprint`; invoke GIMP headlessly with a generated Python batch script.

**Tech Stack:** Python 3 standard library, `unittest`, Scryfall HTTP JSON API, local GIMP command-line batch mode.

---

### Task 1: Pure Helpers

**Files:**
- Create: `thumbnail_generator.py`
- Test: `tests/test_thumbnail_generator.py`

- [ ] Write failing tests for non-empty prompting, slug generation, export filenames, art crop extraction, original-print query generation, and center-crop math.
- [ ] Run `python3 -m unittest tests.test_thumbnail_generator -v` and confirm the tests fail because `thumbnail_generator` does not exist.
- [ ] Implement the tested helpers in `thumbnail_generator.py`.
- [ ] Re-run `python3 -m unittest tests.test_thumbnail_generator -v` and confirm the helper tests pass.

### Task 2: Scryfall Client

**Files:**
- Modify: `thumbnail_generator.py`
- Test: `tests/test_thumbnail_generator.py`

- [ ] Write failing tests using a fake HTTP opener to confirm fuzzy lookup, `oracleid:<id> not:reprint` original-print search, required request headers, and art download behavior.
- [ ] Run the focused tests and confirm they fail because the Scryfall client is not implemented.
- [ ] Implement the Scryfall client with `urllib.request`, JSON parsing, clear errors, and no third-party dependencies.
- [ ] Re-run the focused tests and confirm they pass.

### Task 3: GIMP Runner And CLI

**Files:**
- Modify: `thumbnail_generator.py`
- Test: `tests/test_thumbnail_generator.py`

- [ ] Write failing tests for GIMP batch-script contents and command construction without launching GIMP.
- [ ] Run the focused tests and confirm they fail because GIMP runner construction is not implemented.
- [ ] Implement CLI orchestration, GIMP script generation, headless command execution, export directory creation, and error handling.
- [ ] Re-run all unit tests and confirm they pass.

### Task 4: Verification

**Files:**
- Modify: `thumbnail_generator.py` if verification exposes issues.

- [ ] Run `python3 -m unittest -v`.
- [ ] Run `python3 -m py_compile thumbnail_generator.py tests/test_thumbnail_generator.py`.
- [ ] Attempt a GIMP batch-mode smoke check to verify the installed GIMP can run non-interactively.
- [ ] Report any integration limitation clearly if GIMP batch mode cannot be exercised from the sandbox.
