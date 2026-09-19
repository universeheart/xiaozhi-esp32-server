# Hardware QR activation and unbind

## Factory provisioning

Every sellable unit must first be inserted into `hardware_product_unit`. Unknown, revoked and
scrapped units cannot activate. Example:

```sql
INSERT INTO hardware_product_unit(product_code, serial_number, mac_address, board, manufacture_batch)
VALUES ('COMPANION_V1', 'SN000001', 'fc:0c:70:20:83:a6', 'esp32', '2026-09');
```

The QR JSON contains `productCode`, `serialNumber`, `macAddress`, `issuedAt`, `nonce`, optional
`board`/`appVersion`, and `signature`. The signature is lowercase hex HMAC-SHA256 over:

```text
productCode|serialNumber|normalized-lowercase-mac|issuedAt|nonce
```

`hardware_activation.qr_secret` is a manufacturing/server secret and must never ship in firmware or
the mobile application. Production should inject it from a private deployment configuration.

## Client flow

1. `POST /xiaozhi/hardware/verify` with `{ "qr": { ... } }`.
2. `POST /xiaozhi/hardware/activate` with the same QR, the live device six-digit `activationCode`,
   optional `agentName`, and account token in
   `Authorization: Bearer ...`.
3. To unbind, `POST /xiaozhi/hardware/unbind` with `macAddress`, `confirmation: "UNBIND"`, a unique
   `requestId`, and the account token.

Activation is transactional in manager-api: validate factory registry, create agent, create device,
bind device to agent/account, then write an audit event. Unbind verifies ownership and transactionally
removes chat text/audio, database profiles, agent settings and bindings. Only after that transaction
succeeds does xiaozhi-server remove the matching local `.superbrain_mem` directory.
