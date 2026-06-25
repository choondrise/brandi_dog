# Brandi Dog Online Frontend

Mobile-first Vite frontend for the FastAPI backend in `../backend`.

## Run

```bash
cd frontend
npm install
npm run dev
```

Open the printed Vite URL. By default the frontend calls `http://<current-host>:8000`.

To point at another backend:

```bash
VITE_API_BASE=http://localhost:8000 npm run dev
```

## Card Images

Put card images in:

```text
frontend/public/cards/
```

Expected filenames are:

```text
C2.png, C3.png, ..., C10.png, CJ.png, CQ.png, CK.png, CA.png
D2.png, D3.png, ..., D10.png, DJ.png, DQ.png, DK.png, DA.png
S2.png, S3.png, ..., S10.png, SJ.png, SQ.png, SK.png, SA.png
H2.png, H3.png, ..., H10.png, HJ.png, HQ.png, HK.png, HA.png
joker.png
```

If an image is missing, the UI falls back to the card label.

## Mobile Wrapping

This app is intentionally a static Vite/PWA-style frontend. When the web version is stable, it can be wrapped with Capacitor for iOS/Android while keeping the FastAPI backend as the network service.
