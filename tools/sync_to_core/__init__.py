"""Sync the custom HACS integration to a core-publishable layout.

Generates a copy of `custom_components/neopool/` and `tests/` under
`dist/neopool/`, transforming imports and stripping HACS-specific files
so the result can be diffed against the Home Assistant core repo.

The script is meant to be run manually for now (`python -m tools.sync_to_core`);
later it will be hooked into a CI workflow.
"""
