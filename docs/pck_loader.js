(function () {
	'use strict';

	// Buckshot Roulette web port - main pack loader.
	//
	// Two packs ship side by side because GPU compressed-texture support
	// differs: desktop GPUs decode S3TC (BC1/BC3) but Apple GPUs (iPhone/iPad)
	// cannot, while Apple hardware decodes ASTC natively. The loader probes
	// WebGL2 extensions on a throwaway canvas and picks:
	//   pck/       - S3TC textures  (desktop browsers)
	//   pck-astc/  - ASTC textures  (iOS Safari / Apple GPUs)
	//
	// Chunks are stored in the browser's Cache API (per pack), so repeat
	// visits assemble the pack at local speed with no re-download. Missing
	// chunks download in parallel (streamed, byte-accurate progress) and are
	// placed directly into one preallocated ArrayBuffer, which is handed to
	// Godot via preloadFile - no blob round-trip, one copy less.
	//
	// The manifest carries an md5 version; a rebuilt pack invalidates the
	// cached chunks automatically.

	var CONCURRENCY = 5;

	function pickPackDir() {
		var override = new URLSearchParams(window.location.search).get('pack');
		if (override === 's3tc' || override === 'astc') {
			return override === 'astc' ? 'pck-astc' : 'pck';
		}
		try {
			var probe = document.createElement('canvas');
			var gl = probe.getContext('webgl2');
			if (gl) {
				if (gl.getExtension('WEBGL_compressed_texture_s3tc') ||
					gl.getExtension('WEBGL_compressed_texture_s3tc_srgb')) {
					return 'pck'; // desktop GPUs: BC1/BC3
				}
				if (gl.getExtension('WEBGL_compressed_texture_astc')) {
					return 'pck-astc'; // Apple/mobile GPUs: ASTC
				}
			}
		} catch (e) { /* fall through */ }
		return 'pck'; // safest default
	}

	window.loadPckChunks = function (onProgress) {
		var dir = pickPackDir();
		var cacheName = 'br-pck-' + dir;
		return fetch(dir + '/manifest.json', { cache: 'no-store' })
			.then(function (r) {
				if (r.status === 404) throw { noChunks: true };
				if (!r.ok) throw new Error('failed to load ' + dir + '/manifest.json (HTTP ' + r.status + ')');
				return r.json();
			})
			.catch(function (e) {
				if (e && e.noChunks) return null;
				throw e;
			})
			.then(function (manifest) {
				if (!manifest) return 'godot.pck'; // no chunks: plain single file
				return assemble(dir, cacheName, manifest, onProgress || function () {});
			});
	};

	function assemble(dir, cacheName, manifest, onProgress) {
		// Warm the wasm download while the pack loads (engine.init needs it).
		fetch('godot.wasm').catch(function () {});

		var total = manifest.size || 0;
		var partSizes = manifest.partSizes || [];
		var loaded = 0;
		function tick() { onProgress(loaded, total); }
		tick();

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
					tick();
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
						// stream: byte-accurate progress
						var reader = r.body.getReader();
						var chunks = [];
						var received = 0;
						function pump() {
							return reader.read().then(function (res) {
								if (res.done) return;
								chunks.push(res.value);
								received += res.value.length;
								loaded += res.value.length;
								tick();
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
	}

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
