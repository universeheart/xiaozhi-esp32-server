# Account API

All endpoints return the existing `Result<T>` envelope. Protected endpoints accept the existing
`token` header. The term `combination` is used by every new JSON contract; `password` is retained
only by the legacy manager login for compatibility.

## Authentication

1. `POST /account/auth/status` — check registration/account state.
2. `POST /account/auth/sms/send` — scenes: `REGISTER`, `LOGIN`, `PHONE_CHANGE_OLD`,
   `PHONE_CHANGE_NEW`, `DELETE_ACCOUNT`, `RESET_COMBINATION`.
3. `POST /account/auth/sms/verify` — exchanges an SMS code for a single-use ticket (10 minutes).
4. `POST /account/auth/register` — register using a `REGISTER` ticket; `combination` is optional.
5. `POST /account/auth/login/sms` — login with a `LOGIN` ticket.
6. `POST /account/auth/login/combination` — login with phone and `combination`.

Logging in during the 15-day deletion cooling-off period cancels the deletion request and restores
the account. Locked, suspended and permanently deleted accounts cannot log in.

## Account

- `GET|PUT /account/profile`
- `PUT /account/combination` (current combination or `RESET_COMBINATION` ticket)
- `PUT /account/guardian-pin`, `POST /account/guardian-pin/verify`
- `GET|PUT /account/privacy`
- `GET|POST /account/household/members`, `DELETE /account/household/members/{id}`
- `GET|POST /account/voice-profiles`, `DELETE /account/voice-profiles/{id}`
- `POST /account/phone-change`, `POST /account/phone-change/complete`
- `GET /account/devices`, `POST /account/devices/bind`, `DELETE /account/devices/{id}`
- `POST|DELETE /account/deletion`

Phone change requires two separate tickets. Account deletion requires risk acknowledgement, an SMS
ticket and the current combination when one is configured.

## Media

- `POST /account/media` (`multipart/form-data`: `purpose`, `file`)
- `GET /account/media/{assetId}/content`
- `DELETE /account/media/{assetId}`

Purposes: `AVATAR`, `VOICE_SAMPLE`, `VOICE_MODEL`, `PATROL_VIDEO`, `MEMORY_MEDIA`, `EXPORT`,
`ATTACHMENT`. Downloads and deletes enforce owner identity. Images are limited to 20 MiB, audio to
50 MiB, and video to 200 MiB.
