#!/usr/bin/env python3
"""Assemble the web build directory: engine template + index.html.

Cache/serve details for later: the threaded 4.1 template needs the page to be
cross-origin isolated (COOP/COEP), otherwise SharedArrayBuffer is unavailable.
"""
import json
import os
import shutil
import zipfile

ROOT = os.path.dirname(os.path.abspath(__file__))
WEBPORT = os.path.abspath(os.path.join(ROOT, ".."))
WEB = os.path.join(WEBPORT, "docs")  # docs/ = GitHub Pages "deploy from branch" folder
TEMPLATE_DIR = os.path.join(WEBPORT, "template")
TEMPLATE_ZIP = os.path.join(
    os.environ["APPDATA"], "Godot", "export_templates", "4.1.4.stable", "web_release.zip")

HAS_THREADS = True  # 4.1.x web template is the threaded build


def copy_template():
    os.makedirs(WEB, exist_ok=True)
    names = [
        "godot.js",
        "godot.wasm",
        "godot.worker.js",
        "godot.audio.worklet.js",
        "godot.audio.position.worklet.js",
    ]
    if os.path.isdir(TEMPLATE_DIR):
        for name in names:
            src = os.path.join(TEMPLATE_DIR, name)
            if os.path.exists(src):
                shutil.copyfile(src, os.path.join(WEB, name))
                print("copied", name)
        return
    z = zipfile.ZipFile(TEMPLATE_ZIP)
    for name in names:
        if name in z.namelist():
            with open(os.path.join(WEB, name), "wb") as f:
                f.write(z.read(name))
            print("extracted", name)


def main():
    copy_template()

    pck = os.path.join(WEB, "godot.pck")
    wasm = os.path.join(WEB, "godot.wasm")
    sizes = {"godot.wasm": os.path.getsize(wasm)}
    manifest = os.path.join(WEB, "pck", "manifest.json")
    if os.path.exists(pck):
        sizes["godot.pck"] = os.path.getsize(pck)
    elif os.path.exists(manifest):
        with open(manifest, encoding="utf-8") as f:
            sizes["godot.pck"] = json.load(f)["size"]

    config = {
        "args": [],
        "canvasResizePolicy": 2,
        "executable": "godot",
        "mainPack": "godot.pck",
        "experimentalVFS": False,
        "focusCanvas": True,
        "fileSizes": sizes,
    }

    with open(os.path.join(TEMPLATE_DIR, "godot.html"), encoding="utf-8") as f:
        html = f.read()

    subs = {
        "$GODOT_PROJECT_NAME": "Buckshot Roulette",
        "$GODOT_URL": "godot.js",
        "$GODOT_CONFIG": json.dumps(config),
        "$GODOT_HEAD_INCLUDE": '<meta name="theme-color" content="#000000">',
    }
    for k, v in subs.items():
        assert k in html, k
        html = html.replace(k, v)

    # COOP/COEP shim: GitHub Pages does not send the cross-origin isolation
    # headers the threaded Godot runtime needs for SharedArrayBuffer. This
    # service worker adds them (no-op on localhost, where serve_web.py already
    # sends them). Must be the first script on the page.
    assert "<head>" in html
    html = html.replace(
        "<head>",
        '<head>\n\t\t<script src="coi-serviceworker.js"></script>', 1)

    # Chunked main-pack loader (GitHub Pages rejects files > 100 MB).
    # ($GODOT_URL has already been substituted with "godot.js" above.)
    assert '<script src="godot.js"></script>' in html
    html = html.replace(
        '<script src="godot.js"></script>',
        '<script src="godot.js"></script>\n\t\t<script src="pck_loader.js"></script>', 1)

    # Defer engine start until the pack is assembled in JS. The loader returns
    # either the pack bytes (ArrayBuffer) or a fallback path string; the bytes
    # go straight into preloadFile (no blob-URL fetch round-trip).
    assert "\t\tengine.startGame({" in html
    html = html.replace(
        "\t\tengine.startGame({",
        "\t\t(async () => {\n"
        "\t\t\ttry {\n"
        "\t\t\t\tGODOT_CONFIG['pckData'] = await window.loadPckChunks(function (done, total) {\n"
        "\t\t\t\t\tif (total > 0) {\n"
        "\t\t\t\t\t\tstatusProgressInner.style.width = `${(done / total) * 100}%`;\n"
        "\t\t\t\t\t\tsetStatusMode('progress');\n"
        "\t\t\t\t\t}\n"
        "\t\t\t\t});\n"
        "\t\t\t} catch (err) {\n"
        "\t\t\t\tdisplayFailureNotice(err);\n"
        "\t\t\t\treturn;\n"
        "\t\t\t}\n"
        "\t\t\tconst startOpts = {\n"
        "\t\t\t\t'args': ['--main-pack', 'godot.pck'],", 1)
    assert "\t\t}).then(() => {\n\t\t\tsetStatusMode('hidden');\n\t\t\tinitializing = false;\n\t\t}, displayFailureNotice);\n\t}\n}());" in html
    html = html.replace(
        "\t\t}).then(() => {\n\t\t\tsetStatusMode('hidden');\n\t\t\tinitializing = false;\n\t\t}, displayFailureNotice);\n\t}\n}());",
        "\t\t};\n"
        "\t\tconst pckData = GODOT_CONFIG['pckData'];\n"
        "\t\tconst boot = (typeof pckData === 'string')\n"
        "\t\t\t? engine.startGame(Object.assign({ 'mainPack': pckData }, startOpts))\n"
        "\t\t\t: engine.init(GODOT_CONFIG['executable'])\n"
        "\t\t\t\t.then(function () { return engine.preloadFile(pckData, 'godot.pck'); })\n"
        "\t\t\t\t.then(function () { return engine.start(startOpts); });\n"
        "\t\tboot.then(() => {\n"
        "\t\t\tsetStatusMode('hidden');\n"
        "\t\t\tinitializing = false;\n"
        "\t\t}, displayFailureNotice);\n"
        "\t\t})();\n\t}\n}());", 1)

    # Toggleable on-screen touch controls (Escape / Fullscreen; no joystick).
    assert "</body>" in html
    html = html.replace(
        "</body>",
        '\t<script src="mobile_controls.js"></script>\n</body>')

    with open(os.path.join(WEB, "index.html"), "w", encoding="utf-8") as f:
        f.write(html)
    print("wrote index.html")
    print("sizes:", sizes)


if __name__ == "__main__":
    main()
