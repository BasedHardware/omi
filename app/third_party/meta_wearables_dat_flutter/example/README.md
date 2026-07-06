# meta_wearables_dat_flutter_example

Minimal demo for the `meta_wearables_dat_flutter` plugin. Walks the
happy-path: register glasses with the Meta AI app, request camera
permission, start a video stream into a Flutter `Texture`.

For a richer demo (mock devices, photo capture, full UX) see
[`samples/camera_access/`](../samples/camera_access/) in this repo.

## Run

```sh
flutter pub get
flutter run
```

Make sure the Meta AI app is installed on the same phone with **Developer
Mode** enabled (Settings → Developer Mode), and that your glasses are
already paired in Meta AI.
