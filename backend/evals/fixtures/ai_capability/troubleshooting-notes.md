# Troubleshooting Notes: Saved Chat Loading

## Symptom

Users can sign in and send a chat message, but clicking an older saved chat
shows `Could not load chat` or `Could not load page`.

## Likely causes

1. The conversation file exists but does not have an `owner_username` field.
2. The session cookie is expired and the frontend still renders a stale sidebar.
3. A manual deploy copied only frontend files and left backend conversation
   schema changes out of sync.

## Recommended fix

Run the normal GitHub update path:

```bash
cd ~/.local-ai-os-standard-link-install
./scripts/deploy/ubuntu/update.sh
./scripts/deploy/ubuntu/verify.sh
```

Then ask the user to sign out and sign in again. If the issue remains, inspect
`/app/data/app/conversations` and check whether the conversation JSON files have
`owner_username` set to the expected local account.

## What not to do

Do not delete the entire data directory as the first action. That would remove
uploaded documents, vectors, and saved chats.
