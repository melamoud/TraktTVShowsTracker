# Managing users

Users appear automatically after their first Trakt login.

| Action | Effect |
|--------|--------|
| Disable | Blocks local login; does not touch Trakt |
| Revoke sessions | Ends tracked sessions and clears stored Trakt tokens (must re-login) |
| Delete local | Removes local DB rows for that user; Trakt account unchanged |
| Make admin / Demote | Local admin flag only; cannot demote/delete the last admin |

You cannot disable or delete your own account while using it.
