# Deploy checklist

```bash
cd frontend
rm -rf node_modules/.vite      # Vite's build cache can go stale and silently skip real changes
yarn install
yarn build

cd ..
mkdir -p whatsnext/public/whatsnext_frontend
cp -r frontend/dist/* whatsnext/public/whatsnext_frontend/

cd ..                                # back to bench root
bench build --app whatsnext          # rebuilds Desk assets + relinks public/ — does NOT touch the SPA source
bench --site <site> migrate          # required after any doctype/field/fixture change
bench --site <site> clear-cache
bench restart
```

`www/whatsnext.py` reads `whatsnext/public/whatsnext_frontend/.vite/manifest.json`
(emitted because `vite.config.js` sets `build.manifest: true`) to find the
current hashed JS/CSS filenames at request time. You never need to hand-edit
a filename into `whatsnext.html` — that was the earlier fragile approach and
it's why the build failed before; this manifest lookup fixes it for good. If
you visit `/whatsnext` and see "frontend not built yet", it means the copy
step above didn't run or landed in the wrong folder.

After deploying any frontend change, **test in an Incognito/Private tab first**.
This app is a PWA with a service worker; a browser that already has it
installed will keep serving the old cached bundle even after a fully
successful rebuild. If Incognito shows the fix but a regular tab doesn't,
that confirms it's the service worker, not a deploy failure — clear it via
DevTools → Application → Service Workers → Unregister, then Storage → Clear
site data, then hard refresh.
