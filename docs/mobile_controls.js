(function () {
	'use strict';

	// Buckshot Roulette web port - toggleable on-screen controls (iPad-ready).
	//
	// The game itself is mouse-driven and touches already reach the Godot
	// canvas as mouse input, so no joystick or d-pad is needed. This overlay
	// adds only what touch cannot do on its own:
	//   - Escape (skip intro, back out of menus, close dialogs)
	//   - Fullscreen toggle
	// The panel can be hidden entirely; the small toggle stays reachable.

	var STORE_KEY = 'br_webport_controls_visible';

	function getCanvas() {
		return document.getElementById('canvas') || document.querySelector('canvas');
	}

	function loadVisible() {
		try { return localStorage.getItem(STORE_KEY) !== '0'; } catch (e) { return true; }
	}

	function saveVisible(v) {
		try { localStorage.setItem(STORE_KEY, v ? '1' : '0'); } catch (e) { /* private mode */ }
	}

	function sendEscape() {
		var c = getCanvas();
		if (!c) return;
		var opts = { key: 'Escape', code: 'Escape', keyCode: 27, which: 27, bubbles: true, cancelable: true };
		c.dispatchEvent(new KeyboardEvent('keydown', opts));
		setTimeout(function () {
			c.dispatchEvent(new KeyboardEvent('keyup', opts));
		}, 40);
	}

	function toggleFullscreen() {
		var el = document.documentElement;
		if (document.fullscreenElement || document.webkitFullscreenElement) {
			if (document.exitFullscreen) document.exitFullscreen();
			else if (document.webkitExitFullscreen) document.webkitExitFullscreen();
		} else if (el.requestFullscreen) {
			el.requestFullscreen();
		} else if (el.webkitRequestFullscreen) {
			el.webkitRequestFullscreen(); // iPad Safari
		}
	}

	function makeButton(className, label, title, onTap) {
		var b = document.createElement('button');
		b.className = className;
		b.type = 'button';
		b.title = title;
		b.setAttribute('aria-label', title);
		b.textContent = label;
		// Keep presses away from the canvas so Godot never sees them.
		b.addEventListener('pointerdown', function (e) { e.stopPropagation(); });
		b.addEventListener('pointerup', function (e) { e.stopPropagation(); });
		b.addEventListener('touchstart', function (e) { e.stopPropagation(); }, { passive: true });
		b.addEventListener('touchend', function (e) { e.stopPropagation(); }, { passive: true });
		b.addEventListener('click', function (e) {
			e.stopPropagation();
			onTap();
		});
		b.addEventListener('contextmenu', function (e) { e.preventDefault(); });
		return b;
	}

	var style = document.createElement('style');
	style.textContent = [
		'#br-mobile-controls {',
		'	position: fixed; right: 10px; bottom: 10px; z-index: 1000;',
		'	display: flex; flex-direction: column; align-items: flex-end; gap: 10px;',
		'	font-family: \'Noto Sans\', Arial, sans-serif;',
		'	-webkit-user-select: none; user-select: none;',
		'	-webkit-touch-callout: none;',
		'	pointer-events: none;', /* container lets touches pass through; buttons re-enable */
		'}',
		'#br-mobile-controls .br-panel {',
		'	display: flex; flex-direction: column; gap: 10px;',
		'	pointer-events: auto;',
		'}',
		'#br-mobile-controls .br-panel.br-hidden { display: none; }',
		'#br-mobile-controls button {',
		'	width: 58px; height: 58px; min-width: 44px; min-height: 44px;', /* touch target size */
		'	border-radius: 50%;',
		'	border: 2px solid rgba(255,255,255,0.35);',
		'	background: rgba(20,20,20,0.55);',
		'	color: #e8e8e8;',
		'	font-size: 15px; font-weight: 700; letter-spacing: 0.5px;',
		'	cursor: pointer;',
		'	touch-action: manipulation;',
		'	transition: background 0.15s, transform 0.1s;',
		'}',
		'#br-mobile-controls button:active { background: rgba(60,60,60,0.75); transform: scale(0.94); }',
		'#br-mobile-controls .br-toggle {',
		'	width: 44px; height: 44px; font-size: 17px;',
		'	opacity: 0.55;',
		'	pointer-events: auto;',
		'}',
		'#br-mobile-controls .br-toggle:active { opacity: 0.9; }'
	].join('\n');
	document.head.appendChild(style);

	var root = document.createElement('div');
	root.id = 'br-mobile-controls';

	var panel = document.createElement('div');
	panel.className = 'br-panel';

	var escBtn = makeButton('br-esc', 'ESC', 'Menu / Back (Escape)', sendEscape);
	var fsBtn = makeButton('br-fs', '\u26F6', 'Fullscreen', toggleFullscreen);
	panel.appendChild(escBtn);
	panel.appendChild(fsBtn);

	var toggle = makeButton('br-toggle', '\u2261', 'Show / hide controls', function () {
		var hidden = panel.classList.toggle('br-hidden');
		saveVisible(!hidden);
	});

	root.appendChild(panel);
	root.appendChild(toggle);

	function applyVisibility(v) {
		panel.classList.toggle('br-hidden', !v);
	}
	applyVisibility(loadVisible());

	function boot() {
		document.body.appendChild(root);
	}
	if (document.body) boot();
	else document.addEventListener('DOMContentLoaded', boot);
})();
