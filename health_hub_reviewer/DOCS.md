# Health Hub Reviewer

Writes Health Hub's daily review with Claude, using your existing Claude
subscription.

## Before you start

1. The **Claude Code** add-on must be installed and signed in to Claude. This
   add-on reuses that login (kept in `/homeassistant/.claudecode`); it never asks
   for one itself.
2. Health Hub (the integration) must be installed.

## How it works

Each morning, once last night's sleep has synced, Health Hub writes a summary of
your numbers to `health_hub/review/request.json` in your config folder. This
add-on notices it, asks Claude for a review (with web research, if enabled), and
writes the answer to `health_hub/review/response.json`, which Health Hub shows
on the Health page. You can also ask for a fresh review with the
`health_hub.request_review` action.

## What Claude can do

Only search and read the web. Reading files, running commands and Home Assistant
tools are all switched off, so nothing beyond the summary in the request is
shared. The summary contains numbers such as sleep times, resting heart rate and
step counts, never raw readings or names.

## Options

- **model**: leave empty for your plan's default model.
- **web_research**: let Claude check its observations against current sources.
- **max_turns**: upper limit on Claude's steps per review.
- **timeout_minutes**: give up after this long.

## If the login expires

Sign in again in the Claude Code add-on's terminal (`claude`, then `/login`).
This add-on picks the new login up automatically.
