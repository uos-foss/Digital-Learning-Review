---
name: semver-release
description: Automates semantic versioning pipelines. Use when preparing the app for a new release, updating release logs, or generating tags.
---
# Semantic Versioning & Automated Tagging Workflow

## Core Goals
* Standardize workspace configuration states prior to a production deployment.
* Enforce identical version identities across `app.py`, documentation layouts, and version control tags.

## Instructions
1. **Extract Identity**: Inspect the active variable string value of `__version__` declared in `app.py`.
2. **Increment Mechanics**: Based on the context of updates supplied (patch, minor, or major feature changes), adjust the value strictly according to SemVer definitions (X.Y.Z).
3. **Update Downstream Docs**: Mirror the newly created string version inside `views/docs.py` or your historical release notes log.
4. **Git Artifact Alignment**: Commit the altered codebase files using a standardized commit summary format (e.g., `Release version 1.7.1`), then generate a matching tag identifier prefixed with a `v` character (`v1.7.1`).

## Constraints
* Never generate or push a release tag identifier unless all modifications pass localized syntactic checks.