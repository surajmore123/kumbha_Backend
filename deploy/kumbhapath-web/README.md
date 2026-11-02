# Files for https://kumbhapath.in

Invitation links look like this:

    https://kumbhapath.in/join/family#t=<token>

kumbhapath.in is the Next.js site behind Cloudflare and the nginx container from
the KumbhaPath repo (`/root/KumbhaPath`). That repo isn't this one, so nothing
here takes effect until the steps below are done on the server.

| File | Published at |
|---|---|
| `.well-known/assetlinks.json` | `https://kumbhapath.in/.well-known/assetlinks.json` |
| `.well-known/apple-app-site-association` | `https://kumbhapath.in/.well-known/apple-app-site-association` |
| `join-family.html` | `https://kumbhapath.in/join/family` |
| `safety-qr.html` | `https://kumbhapath.in/safety/qr` |
| `nginx-kumbhapath.conf` | Pasted into the nginx config |

`app_identity.json` is the only file to edit by hand. `build_association_files.py`
writes the two association files from it.

**The files in `.well-known/` today are for testing only.** They hold the placeholder
`com.example` IDs and this development machine's debug key, and the Apple file has no
Team ID. Don't publish them.

## 1. Fill in the identity

Edit `app_identity.json`:

| Field | Value |
|---|---|
| `android_package` | The final Android application ID |
| `android_sha256` | The release signing SHA-256, in `AA:BB:...` form. With Play App Signing, use the "App signing key certificate" from Play Console > Setup > App signing, and add the upload key too if you test upload-signed builds |
| `android_debug_sha256` | Leave as is. It's left out of production files |
| `ios_bundle_id` | The final iOS bundle ID |
| `apple_team_id` | The 10-character Team ID from developer.apple.com > Membership |

Then build. This stops with a list of problems if anything is missing:

```bash
python deploy/kumbhapath-web/build_association_files.py --production
```

## 2. Put the files on the server

1. Copy this folder to the server, for example `/root/KumbhaPath/deploy/kumbhapath-web`.
2. In the KumbhaPath compose file, mount it into the nginx service:

   ```yaml
   volumes:
     - ./deploy/kumbhapath-web:/srv/kumbhapath-web:ro
   ```

3. Paste `nginx-kumbhapath.conf` into the `server` block for `kumbhapath.in`, above the
   location that proxies to Next.js. The file is probably under
   `deploy/nginx/sites/`, but that repo wasn't available to check.
4. Recreate nginx so the mount applies, after testing the config:

   ```bash
   docker compose up -d nginx
   docker compose exec nginx nginx -t
   docker compose exec nginx nginx -s reload
   ```

`.well-known` isn't used on the live site today: both paths returned Next.js 404s
on 31 Oct 2026.

## 3. Check Cloudflare

Google and Apple must reach both files with no challenge page or redirect.

- Purge these two URLs and `/join/family` after every change.
- If Bot Fight Mode or a WAF rule is on, add a skip rule for `/.well-known/*`.

## 4. Deploy the backend and app

Run `python manage.py migrate family` (adds one nullable column), then release the app.
Publish the association files before the app reaches users, because Android checks them
when the app is installed.

## 5. Check production

```bash
curl -i https://kumbhapath.in/.well-known/assetlinks.json
curl -i https://kumbhapath.in/.well-known/apple-app-site-association
curl -i https://kumbhapath.in/join/family
```

Each must return `200` directly. The first two must be `application/json`.

- Google's checker:
  `https://digitalassetlinks.googleapis.com/v1/statements:list?source.web.site=https://kumbhapath.in&relation=delegate_permission/common.handle_all_urls`
- On an Android phone with the store build:

  ```bash
  adb shell pm get-app-links <package>
  ```

  `kumbhapath.in` must show `verified`.
- Apple's CDN copy: `https://app-site-association.cdn-apple.com/a/v1/kumbhapath.in`.
  It can take hours to update.

## Adding store links

The page has no store links because the app isn't published yet. Add them to
`join-family.html` once it is.
