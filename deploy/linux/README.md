# Ubuntu / Debian Docker deployment

Copy the complete release directory to the target server. It must contain:

- `deploy-linux.sh`
- `compose.yaml`
- `.env.example`
- `config_from_api.yaml`
- `xiaozhi-images-linux-amd64-<tag>.tar`
- `SHA256SUMS`

Docker must already be installed and running. Run:

```bash
chmod +x deploy-linux.sh
sudo ./deploy-linux.sh
```

The script initializes `.env`, generates database passwords, verifies and loads the offline images, copies `data/.config.yaml`, starts the management services, asks for `server.secret`, starts all services, and configures UFW when it is active.

For non-interactive continuation after the first administrator has been registered:

```bash
sudo ./deploy-linux.sh \
  --server-secret 'your-server.secret' \
  --public-host '192.168.1.20'
```

Use `--skip-image-load` when the images have already been loaded and `--skip-firewall` when firewall rules are managed elsewhere.
