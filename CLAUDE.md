# CLAUDE.md

This file provides guidance for AI assistants working in this repository.

## Repository Overview

A minimal utility repository containing a single Python script for expanding numeric ranges (e.g., port ranges) into individual values.

## Structure

```
scripts/
├── CLAUDE.md         # This file
├── README.md         # Project title
└── expand_pc.py      # Port/config range expansion utility
```

## Script: expand_pc.py

**Purpose:** Expands compact range notation (e.g., `"1000-1920, 2000-2239"`) into a flat comma-separated list of individual integers.

**Key function:**
```python
def expand_ranges(ranges):
    # Input:  "1000-1920, 2000-2239"
    # Output: [1000, 1001, ..., 1920, 2000, ..., 2239]
```

**Hardcoded ranges:** `"1000-1920, 2000-2239, 2555-2574, 2740-2786"` (~1,228 values total)

**Run:**
```bash
python3 expand_pc.py
```

**Output:** A single line of comma-separated integers printed to stdout.

## Tech Stack

- Language: Python 3
- Dependencies: None (standard library only)
- No build, install, or test steps required

## Conventions

- No external dependencies — keep it standard library only
- The range string format is `"START-END"` pairs separated by `", "` (comma + space)
- `expand_ranges()` is inclusive on both ends (`range(start, end + 1)`)

## Development Workflow

### Branching

Feature branches follow the pattern `claude/<description>-<id>` (e.g., `claude/add-claude-documentation-AUQuN`). Develop on the designated branch and push when complete:

```bash
git push -u origin <branch-name>
```

### Making Changes

1. Edit the relevant file(s)
2. Test locally: `python3 expand_pc.py`
3. Commit with a clear message
4. Push to the feature branch

### Modifying the Ranges

To change which ranges are expanded, update the `ranges` string at line 9 of `expand_pc.py`. The format must be `"START-END"` pairs joined by `", "` (note the space after the comma — the parser splits on `", "`).

## Notes for AI Assistants

- This is a small, single-purpose repo — avoid over-engineering changes
- Do not add external dependencies
- Do not add a test framework unless explicitly requested
- Do not parameterize the script (CLI args, config files) unless asked
- If modifying `expand_ranges()`, preserve the inclusive end behavior
