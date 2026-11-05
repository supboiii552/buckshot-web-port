# Buckshot Roulette — browser port (personal use)

A web port of **Buckshot Roulette** (v2.2.0.6, Steam/Godot 4.1.1) that runs the
game's own original data pack in a stock **Godot 4.1.4** web runtime — no game
code was rewritten. Built from a personally owned copy of the game. Not
affiliated with or endorsed by Mike Klubnika / Critical Reflex.

> **Ownership note:** `web/` contains the full commercial game. Hosting it on
> a public GitHub Pages site means redistributing the game publicly; private
> repos need a paid plan for Pages. That tradeoff is the owner's call — this
> repo was built for personal/local play.

## What works

- Full single-player game: menu → intro → club, all rounds, items, dealer.
- Verified in-browser: clean boot (`user entered scene: menu`), zero resource
  or shader errors, zero WebGL texture-upload errors.
- Toggleable touch controls for iPad (bottom-right): **ESC** (skip/back),
  **fullscreen**, and a collapse toggle. No joystick — the game is
  mouse-driven and touch already reaches the canvas as mouse input.
- Saves persist in the browser's IndexedDB (`user://` storage).

## Known limitations

- Steam features are stubbed (`web` build has no Steamworks): multiplayer,
  achievements, leaderboards and friends are inactive.
- The web runtime uses Godot's Compatibility (WebGL2) renderer, while the
  desktop game uses Forward+ (Vulkan) — expect minor lighting/shading
  differences.
- First load downloads ~443 MB (split into 5 chunks because GitHub rejects
  files > 100 MB; reassembled in the browser before boot).

## Repo layout

```
web/          deployable site (everything GitHub Pages needs)
tools/        build + serve pipeline (Python 3, needs Pillow + numpy)
game_data/    extracted original PCK (not committed — proprietary game data)
build/        intermediate build trees (not committed)
template/     Godot 4.1.4 web template files (not committed)
certs/        self-signed TLS cert for LAN HTTPS (never commit private keys)
```

## Build pipeline (only needed after changing assets or tools)

```sh
python tools/shrink_textures.py --src game_data --out build/assets   # resize + WebGL2 fixes
python tools/reencode_audio.py                                       # smaller audio
python tools/build_full.py       # full resource tree + Steam stub + autoload patch
python tools/build_pack.py       # -> web/godot.pck
python tools/assemble_web.py     # -> web/index.html (injects controls + loader)
python tools/split_pck.py        # -> web/pck/*.partNN (Pages-ready)
```

Texture notes (why `shrink_textures.py` exists):
WebGL2 rejects compressed textures whose width/height are not multiples of 4 —
the original pack has 253 such textures, which upload fine on desktop OpenGL
but fail silently in browsers (untextured/black objects). The tool also
preserves BC1a (DXT1 1-bit alpha) cutouts and keeps player-read documents
(the waiver) at full resolution.

## Run locally

```sh
python tools/serve_web.py 8124            # http://127.0.0.1:8124/
python tools/serve_web.py 8124 --https    # iPad on LAN: https://<pc-ip>:8124/
```

`--https` uses the self-signed cert in `certs/` (create with
`python tools/make_cert.py`); accept the browser warning once. iOS Safari
requires a secure context before it grants SharedArrayBuffer, which the
threaded Godot runtime needs.

## Publish to GitHub Pages

1. Push this folder to a GitHub repository (respecting the `.gitignore`).
2. Repo **Settings → Pages → Build and deployment → Source: GitHub Actions**.
3. The included workflow (`.github/workflows/deploy_pages.yml`) deploys `web/`
   on every push to `main`.
4. Open `https://<user>.github.io/<repo>/`. On the first visit the
   COOP/COEP service worker registers and the page reloads once — that is
   expected. Then the pack loads (~443 MB) and the game boots.
