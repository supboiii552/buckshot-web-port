(function () {
	'use strict';

	// Buckshot Roulette web port - main pack loader.
	//
	// GitHub Pages rejects files > 100 MB, so the pack ships as chunks in pck/
	// (tools/split_pck.py). This loader:
	//   1. warms the HTTP cache for godot.wasm in parallel (engine.init would
	//      otherwise only start fetching it after all chunks are in),
	//   2. keeps downloaded chunks in the browser's Cache API, so repeat visits
	//      load at disk speed instead of re-downloading ~443 MB,
	//   3. downloads missing chunks with limited concurrency, reporting
	//      byte-accurate progress,
	//   4. assembles everything into a Blob and resolves a blob: URL that
	//      Godot's loader fetches like any file (startGame -> preloadFile).
	//
	// The manifest carries a version (md5 of the whole pack). A rebuilt pack
	// invalidates the cached chunks automatically; a partial/failed first
	// download is retried from the network.

	var CACHE_NAME = 'br-pck-v1';
	var VERSION_KEY = 'pck/version.json';
	var CONCURRENCY = 3;

	window.loadPckChunks = function (onProgress) {
		return fetch('pck/manifest.json', { cache: 'no-store' })
			.then(function (r) {
				if (r.status === 404) throw { noChunks: true };
				if (!r.ok) throw new Error('failed to load pck/manifest.json (HTTP ' + r.status + ')');
				return r.json();
			})
			.catch(function (e) {
				if (e && e.noChunks) return null;
				throw e;
			})
			.then(function (manifest) {
				if (!manifest) return 'godot.pck'; // no chunks (plain local serving)
				return assemble(manifest, onProgress || function () {});
			});
	};

	function assemble(manifest, onProgress) {
		// Warm the wasm download while the pack is loading.
		fetch('godot.wasm').catch(function () {});

		var total = manifest.size || 0;
		var loaded = 0;
		function tick() { onProgress(loaded, total); }
		tick();

		var cacheP;
		try {
			cacheP = window.caches && window.caches.open
				? window.caches.open(CACHE_NAME).catch(function () { return null; })
				: Promise.resolve(null);
		} catch (e) {
			cacheP = Promise.resolve(null);
		}

		return cacheP.then(function (cache) {
			return withCacheState(cache, manifest);
		}).then(function (state) {
			var blobs = new Array(manifest.parts.length);
			var next = 0;

			function store(i, buf) {
				loaded += buf.byteLength;
				tick();
				blobs[i] = new Blob([buf]);
				if (state.cache) {
					state.cache.put(manifest.parts[i], new Response(buf)).catch(function () {});
				}
			}

			function ensurePart(i) {
				var name = manifest.parts[i];
				if (state.have[i] && state.cache) {
					return state.cache.match(name).then(function (hit) {
						if (hit) return hit.arrayBuffer().then(function (buf) { store(i, buf); });
						return download(i); // evicted individually: refetch
					});
				}
				return download(i);
			}

			function download(i) {
				var name = manifest.parts[i];
				return fetch(name).then(function (r) {
					if (!r.ok) throw new Error('failed to fetch ' + name + ' (HTTP ' + r.status + ')');
					return r.arrayBuffer();
				}).then(function (buf) {
					store(i, buf);
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
				// Record the version only once every chunk is safely in the cache.
				if (state.cache) {
					state.cache.put(VERSION_KEY,
						new Response(JSON.stringify({ version: manifest.version }))).catch(function () {});
				}
				return URL.createObjectURL(
					new Blob(blobs, { type: 'application/octet-stream' }));
			});
		});
	}

	function withCacheState(cache, manifest) {
		if (!cache) return Promise.resolve({ cache: null, have: [] });
		// Only trust cached chunks when the recorded pack version matches.
		return cache.match(VERSION_KEY).then(function (vres) {
			if (!vres) return { cache: cache, have: [] };
			return vres.json().then(function (v) {
				if (v && v.version === manifest.version) {
					return Promise.all(manifest.parts.map(function (name) {
						return cache.match(name).then(function (hit) { return !!hit; })
							.catch(function () { return false; });
					})).then(function (have) {
						return { cache: cache, have: have };
					});
				}
				// Pack was rebuilt: drop everything cached under this name.
				return window.caches.delete(CACHE_NAME).then(function () {
					return window.caches.open(CACHE_NAME);
				}).then(function (fresh) {
					return { cache: fresh, have: [] };
				});
			}).catch(function () { return { cache: cache, have: [] }; });
		}).catch(function () { return { cache: null, have: [] }; });
	}
})();
