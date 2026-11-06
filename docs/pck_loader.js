(function () {
	'use strict';

	// Buckshot Roulette web port - main pack loader.
	//
	// Two packs are downloaded and mounted instead of one, which both keeps
	// the GitHub Pages tree under its 1 GB limit and stops shipping the same
	// non-texture content to every device:
	//
	//   base/               - project, scripts, scenes, audio (shared)
	//   tex-s3tc/           - BC1/BC3 textures   - desktop browsers
	//   tex-etc2/           - ETC2/EAC textures  - Apple GPUs etc. (mobile)
	//   tex-rgba/           - RGB8/RGBA8/RG8     - anything that can't upload
	//                         compressed textures at all
	//
	// The choice matters because Godot 4.1.4's GLES3 backend gates compressed
	// uploads on GL extension names: S3TC only via WEBGL_compressed_texture_s3tc
	// (desktop Chrome/Firefox have it, Safari does not), ETC2 unconditionally
	// (config.cpp hardcodes etc2_supported=true on GLES builds; iOS Safari
	// accepts ETC2 since 13.4 via WEBGL_compressed_texture_etc). ASTC would be
	// rejected by this engine build on every browser - it checks only GL-style
	// names (GL_KHR_texture_compression_astc_ldr...) that browsers never report,
	// then has no software decoder to fall back on.
	//
	// The engine boots from base.pck ("--main-pack base.pck"); the overlay
	// buffer is preloaded as res://tex.pck and mounted by the BootPack
	// autoload with replace_files=true. (See tools/boot_pack.gd.)
	//
	// Chunks are stored in the browser's Cache API (per pack), so repeat
	// visits assemble the packs at local speed with no re-download. Missing
	// chunks download in parallel (streamed, byte-accurate progress) and are
	// placed directly into one preallocated ArrayBuffer, which is handed to
	// Godot via preloadFile - no blob round-trip.
	//
	// Each manifest carries an md5 version; a rebuilt pack invalidates its
	// cached chunks automatically. A small on-screen badge reports which
	// overlay was picked, so a device that renders blank textures is
	// diagnosable without devtools.

	var CONCURRENCY = 5;

	function gl2() {
		try {
			return document.createElement('canvas').getContext('webgl2');
		} catch (e) {
			return null;
		}
	}

	function uploadTest(internalFormat, block, w, h) {
		var gl = gl2();
		if (!gl) return false;
		gl.getExtension('WEBGL_compressed_texture_etc');
		gl.getExtension('WEBGL_compressed_texture_s3tc');
		try {
			var tex = gl.createTexture();
			gl.bindTexture(gl.TEXTURE_2D, tex);
			gl.texParameteri(gl.TEXTURE_2D, gl.TEXTURE_MIN_FILTER, gl.NEAREST);
			gl.texParameteri(gl.TEXTURE_2D, gl.TEXTURE_MAG_FILTER, gl.NEAREST);
			gl.compressedTexImage2D(gl.TEXTURE_2D, 0, internalFormat, w, h, 0, block);
			return gl.getError() === 0;
		} catch (e) {
			return false;
		}
	}

	// One valid ETC2 RGB8 block (4x4) and one EAC RG11 block pair (4x4).
	var ETC2_RGB8_BLOCK = new Uint8Array([0x80, 0x81, 0x04, 0x0a, 0x01, 0x00, 0x02, 0x20]);
	var EAC_RG11_BLOCK = new Uint8Array([
		0x06, 0x11, 0x24, 0x90, 0x00, 0x92, 0x4b, 0x6d,
		0x06, 0x11, 0x22, 0x52, 0x25, 0x22, 0x52, 0x25]);

	function etc2Works() {
		return uploadTest(0x9274, ETC2_RGB8_BLOCK, 4, 4) &&
			uploadTest(0x9272, EAC_RG11_BLOCK, 4, 4);
	}

	function pickTexDir() {
		var override = new URLSearchParams(window.location.search).get('pack');
		if (override === 'etc2' || override === 's3tc' || override === 'rgba') {
			return 'tex-' + override;
		}
		try {
			var gl = gl2();
			if (gl && (gl.getExtension('WEBGL_compressed_texture_s3tc') ||
					gl.getExtension('WEBGL_compressed_texture_s3tc_srgb'))) {
				return 'tex-s3tc'; // desktop GPUs: BC1/BC3 in hardware
			}
		} catch (e) { /* fall through */ }
		// Mobile/other: ETC2 if this browser actually accepts the uploads
		// (Safari iOS 13.4+), otherwise uncompressed RGBA8 - which renders
		// on every WebGL2 device, no extension required.
		return etc2Works() ? 'tex-etc2' : 'tex-rgba';
	}

	function showBadge(text) {
		try {
			var b = document.createElement('div');
			b.id = 'pack-badge';
			b.style.cssText = 'position:fixed;right:4px;bottom:4px;z-index:2147483647;' +
				'color:#fff;background:rgba(0,0,0,0.5);font:10px/1.25 monospace;' +
				'padding:2px 5px;border-radius:3px;pointer-events:none;opacity:0.85';
			b.textContent = text;
			(document.body || document.documentElement).appendChild(b);
		} catch (e) { /* cosmetic only */ }
	}

	function fetchManifest(dir) {
		return fetch(dir + '/manifest.json', { cache: 'no-store' })
			.then(function (r) {
				if (!r.ok) {
					throw new Error('failed to load ' + dir + '/manifest.json (HTTP ' + r.status + ')');
				}
				return r.json();
			});
	}

	// Assembles one pack from its chunk manifest. `tick` receives no data;
	// the caller owns the shared (loaded, total) counters.
	window.__assemblePck = function (dir, cacheName, manifest, tick) {
		var total = manifest.size || 0;
		var partSizes = manifest.partSizes || [];
		var loaded = 0;
		var onTick = function (d) { tick(d, total); };

		// One contiguous buffer; each worker writes only its own slice.
		var out = new Uint8Array(total);
		var done = new Uint8Array(manifest.parts.length);
		var next = 0;

		var cacheP;
		try {
			cacheP = window.caches && window.caches.open
				? window.caches.open(cacheName).catch(function () { return null; })
				: Promise.resolve(null);
		} catch (e) {
			cacheP = Promise.resolve(null);
		}

		return cacheP.then(function (cache) {
			return cacheState(cache, dir, cacheName, manifest).then(function (state) {
				function storePart(i, buf) {
					out.set(new Uint8Array(buf), sumBefore(i));
					loaded += buf.byteLength;
					done[i] = 1;
					onTick(buf.byteLength);
					if (state.cache) {
						state.cache.put(manifest.parts[i], new Response(buf)).catch(function () {});
					}
				}

				function sumBefore(i) {
					var ofs = 0;
					for (var k = 0; k < i; k++) ofs += partSizes[k];
					return ofs;
				}

				function ensurePart(i) {
					var name = manifest.parts[i];
					if (state.have[i] && state.cache) {
						return state.cache.match(name).then(function (hit) {
							if (hit) {
								return hit.arrayBuffer().then(function (buf) {
									storePart(i, buf);
								});
							}
							return download(i);
						});
					}
					return download(i);
				}

				function download(i) {
					var name = manifest.parts[i];
					return fetch(name).then(function (r) {
						if (!r.ok) throw new Error('failed to fetch ' + name + ' (HTTP ' + r.status + ')');
						if (!r.body) return r.arrayBuffer();
						// stream into one buffer; storePart owns the progress ticks
						var reader = r.body.getReader();
						var received = 0;
						var chunks = [];
						function pump() {
							return reader.read().then(function (res) {
								if (res.done) return;
								chunks.push(res.value);
								received += res.value.length;
								return pump();
							});
						}
						return pump().then(function () {
							var buf = new Uint8Array(received);
							var pos = 0;
							chunks.forEach(function (c) { buf.set(c, pos); pos += c.length; });
							if (partSizes[i] && buf.byteLength !== partSizes[i]) {
								throw new Error('chunk ' + name + ' size mismatch');
							}
							return buf.buffer;
						});
					}).then(function (buf) {
						storePart(i, buf);
					});
				}

				var workers = [];
				for (var w = 0; w < CONCURRENCY; w++) {
					workers.push((function loop() {
						if (next >= manifest.parts.length) return Promise.resolve();
						var i = next++;
						return ensurePart(i).then(loop);
					})());
				}

				return Promise.all(workers).then(function () {
					for (var k = 0; k < done.length; k++) {
						if (!done[k]) throw new Error('chunk ' + manifest.parts[k] + ' missing');
					}
					if (state.cache) {
						state.cache.put(dir + '/version.json',
							new Response(JSON.stringify({ version: manifest.version })))
							.catch(function () {});
					}
					return out.buffer; // ArrayBuffer for engine.preloadFile
				});
			});
		});
	};

	window.loadPckChunks = function (onProgress) {
		var tex = pickTexDir();
		if (tex === 'tex-etc2' && !etc2Works()) {
			// The upload probe rejected ETC2: do not ship a pack this
			// browser cannot render. Uncompressed RGBA8 needs no extension
			// and renders everywhere WebGL2 does.
			console.warn('ETC2 upload test failed - falling back to tex-rgba');
			tex = 'tex-rgba';
		}
		var label = tex.replace('tex-', '');
		var always = function () { /* cosmetic */ };
		showBadge('pack: base+' + label + ' | probe ' + (tex === 'tex-rgba' ? 'n/a' : 'ok'));

		var loaded = 0;
		var total = 0;
		var progress = onProgress || function () {};
		function tick(delta) {
			loaded += delta;
			if (total > 0) progress(loaded, total);
		}
		// Warm the wasm download while the packs load (engine.init needs it).
		fetch('godot.wasm').catch(always);

		return Promise.all([fetchManifest('base'), fetchManifest(tex)]).then(function (ms) {
			total = ms[0].size + ms[1].size;
			return window.__assemblePck('base', 'br-pck-base', ms[0], tick).then(function (baseBuf) {
				return window.__assemblePck(tex, 'br-pck-' + tex, ms[1], tick).then(function (texBuf) {
					return { base: baseBuf, tex: texBuf };
				});
			});
		});
	};

	function cacheState(cache, dir, cacheName, manifest) {
		if (!cache) return Promise.resolve({ cache: null, have: [] });
		// Only trust cached chunks when the recorded pack version matches.
		var versionKey = dir + '/version.json';
		return cache.match(versionKey).then(function (vres) {
			if (!vres) return { cache: cache, have: [] }; // first visit
			return vres.json().then(function (v) {
				if (v && v.version === manifest.version) {
					return Promise.all(manifest.parts.map(function (name) {
						return cache.match(name).then(function (hit) { return !!hit; })
							.catch(function () { return false; });
					})).then(function (have) {
						return { cache: cache, have: have };
					});
				}
				// Pack was rebuilt: drop everything cached for this pack.
				return window.caches.delete(cacheName).then(function () {
					return window.caches.open(cacheName);
				}).then(function (fresh) {
					return { cache: fresh, have: [] };
				});
			}).catch(function () { return { cache: cache, have: [] }; });
		}).catch(function () { return { cache: null, have: [] }; });
	}
})();
