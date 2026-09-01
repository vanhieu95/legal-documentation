# Vendored frontend assets

These browser assets are copied from exact packages in `package-lock.json`; the application never
loads a CDN. `manifest.json` records the npm package, version, source path, SPDX license, destination,
and SHA-256 checksum for each committed file.

```bash
npm ci
npm run assets:vendor
npm run assets:verify
```

The Alpine file is the official CSP-friendly build. Do not replace it with the standard Alpine CDN
build, which requires runtime expression evaluation. Review package licenses and the generated diff
whenever a pin changes.
