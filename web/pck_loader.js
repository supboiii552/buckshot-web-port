(function () {
	'use strict';

	// Buckshot Roulette web port - main pack loader.
	//
	// GitHub Pages rejects files larger than 100 MB, so the 440+ MB pack is
	// stored as chunks in pck/ (see tools/split_pck.py). This loader fetches
	// the chunks, assembles them into a Blob (browser-managed, so only one
	// chunk sits in JS memory at a time) and resolves to a blob: URL that
	// Godot's loader fetches like any other file (startGame -> preloadFile).
	//
	// If no chunk manifest exists (e.g. plain local serving with a single
	// godot.pck), it falls back to that file directly.

	window.loadPckChunks = function (onProgress) {
		return fetch('pck/manifest.json', { cache: 'no-store' })
			.then(function (r) {
				if (r.status === 404) {
					throw { noChunks: true };
				}
				if (!r.ok) {
					throw new Error('failed to load pck/manifest.json (HTTP ' + r.status + ')');
				}
				return r.json();
			})
			.catch(function (e) {
				if (e && e.noChunks) {
					return null; // no chunks available: use the single pack
				}
				throw e;
			})
			.then(function (manifest) {
				if (!manifest) {
					return 'godot.pck';
				}
				var blobs = [];
				var loaded = 0;
				var chain = Promise.resolve();
				manifest.parts.forEach(function (name) {
					chain = chain.then(function () {
						return fetch(name).then(function (r) {
							if (!r.ok) {
								throw new Error('failed to fetch ' + name + ' (HTTP ' + r.status + ')');
							}
							return r.arrayBuffer();
						}).then(function (buf) {
							loaded += buf.byteLength;
							blobs.push(new Blob([buf])); // hand off to blob storage, free the buffer
							if (onProgress) {
								onProgress(loaded, manifest.size);
							}
						});
					});
				});
				return chain.then(function () {
					return URL.createObjectURL(
						new Blob(blobs, { type: 'application/octet-stream' }));
				});
			});
	};
})();
