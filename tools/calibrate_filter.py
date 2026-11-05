#!/usr/bin/env python3
"""Fit a CSS brightness/contrast/saturation filter that maps the web render
onto the desktop (Forward+ ACES + color-adjustments) look.

Ground truth: diag/desktop_ref.png (the real game at the table) vs
diag/web_table.png (the web port, same scene). The felt region of each is
sampled; a parametric CSS-style transform
    y = saturate( contrast( brightness(x) ) )
is fitted per the Godot adjustment order (brightness -> contrast -> saturation;
CSS applies functions in written order and clamps per step).

CSS saturate() uses Rec.709 luma weights, Godot uses 1/3 each - simulated with
the CSS weights since that is what the browser will execute.
"""
import numpy as np
from PIL import Image

REF = r"C:\Users\eight\Downloads\Buckshot Roulette_windows\webport\diag\desktop_ref.png"
WEB = r"C:\Users\eight\Downloads\Buckshot Roulette_windows\webport\diag\web_table.png"
OUT = r"C:\Users\eight\Downloads\Buckshot Roulette_windows\webport\diag\web_table_filtered.png"

ref = np.asarray(Image.open(REF).convert("RGB"), np.float32) / 255.0
web = np.asarray(Image.open(WEB).convert("RGB"), np.float32) / 255.0
Hw, Ww = web.shape[:2]
Hr, Wr = ref.shape[:2]
print("desktop:", ref.shape, " web:", web.shape)

# --- felt sample boxes -------------------------------------------------------
# desktop: full frame minus HUD overlay (top-right) - felt occupies center/lower
ref_box = ref[int(Hr * 0.60):int(Hr * 0.95), int(Wr * 0.30):int(Wr * 0.62)]
# web: game view sits between browser chrome and letterbox; felt is central
web_box = web[int(Hw * 0.28):int(Hw * 0.72), int(Ww * 0.28):int(Ww * 0.72)]

def sample(img, n=6000, seed=1):
    h, w = img.shape[:2]
    rng = np.random.default_rng(seed)
    ys = rng.integers(0, h, n)
    xs = rng.integers(0, w, n)
    return img[ys, xs]  # (n,3) in 0..1

ref_s = sample(ref_box, seed=2)
web_s = sample(web_box, seed=3)

for name, s in (("desktop felt", ref_s), ("web felt", web_s)):
    med = np.median(s, axis=0) * 255
    q10, q90 = np.percentile(s, [10, 90], axis=0) * 255
    print(f"{name}: median RGB {med.round(1)}, p10 {q10.round(1)}, p90 {q90.round(1)}")

# --- CSS-style transform ------------------------------------------------------
LUMA = np.array([0.2126, 0.7152, 0.0722], np.float32)

def css_transform(px, a, b, c):
    y = px * a                      # brightness
    y = np.clip(y, 0.0, 1.0)
    y = (y - 0.5) * b + 0.5         # contrast
    y = np.clip(y, 0.0, 1.0)
    gray = y @ LUMA
    gray = gray[..., None]
    y = gray + (y - gray) * c   # saturation
    return np.clip(y, 0.0, 1.0)

# match quantiles per channel
QS = [10, 25, 50, 75, 90]
ref_q = np.percentile(ref_s, QS, axis=0)   # (5,3)

best = None
for a in np.arange(0.40, 1.01, 0.02):
    for b in np.arange(0.70, 1.51, 0.025):
        for c in np.arange(0.6, 1.81, 0.05):
            y = css_transform(web_s, a, b, c)
            yq = np.percentile(y, QS, axis=0)
            loss = float(np.mean((yq - ref_q) ** 2))
            if best is None or loss < best[0]:
                best = (loss, a, b, c)
loss, a, b, c = best
print(f"\nbest fit: brightness={a:.2f} contrast={b:.2f} saturate={c:.2f} (quantile MSE {loss:.5f})")

# report the fitted transform on the medians
med_w = np.median(web_s, axis=0)
med_t = np.median(css_transform(web_s, a, b, c), axis=0)
med_r = np.median(ref_s, axis=0)
print("web median -> fitted:", (med_w * 255).round(1), "->", (med_t * 255).round(1),
      "  desktop:", (med_r * 255).round(1))

# --- apply to the full web frame for a visual check ---------------------------
full = css_transform(web, a, b, c)
Image.fromarray((full * 255).astype(np.uint8)).save(OUT)
print("wrote", OUT)
print(f"\nCSS: filter: brightness({a:.2f}) contrast({b:.2f}) saturate({c:.2f});")
