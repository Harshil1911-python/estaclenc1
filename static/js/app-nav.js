/*
 * Estacle persistent-shell navigation.
 *
 * Every page is still a normal, fully server-rendered Flask page (same routes, same
 * auth decorators). This script only changes HOW internal navigation is performed:
 * instead of tearing the whole document down (which rebuilds the sidebar and flashes),
 * it fetches the same URL and swaps only the content region of .app-layout (everything
 * next to the sidebar: normally <main class="main-content">, or the display-properties
 * layout). The sidebar element itself is never touched.
 *
 *   - Without JavaScript (or if anything unexpected happens) links and forms behave
 *     exactly as before: normal full-page navigation.
 *   - Authorization is untouched: the request goes to the same protected route with the
 *     session cookie, so a redirect to /login or a "no permission" redirect is followed
 *     and the final URL is shown.
 *
 * This file must be loaded synchronously (no defer/async), inside the sidebar partial, so it
 * runs before the page's own inline scripts and can record the document/window listeners
 * they register (needed to remove them again when the page is swapped out).
 *
 * Opt-outs: add  data-no-ajax  to any <a> or <form> to force a normal page load.
 *
 * Authoring note for page scripts: inline <script>s in a page are re-run on every visit,
 * wrapped in a block so top-level const/let do not collide. Functions declared with
 * `function name(){}` (or assigned to window) stay reachable from inline onclick="..."
 * attributes; a top-level `const name = () => {}` is NOT visible to inline attributes.
 * document/window listeners added by page scripts are removed automatically on the next
 * navigation so they never accumulate.
 */
(function () {
  'use strict';

  if (window.__estacleNav) return;

  var layout = document.querySelector('.app-layout');
  var sidebar = layout ? childSidebar(layout) : null;
  if (!layout || !sidebar || !window.fetch || !window.DOMParser ||
      !window.history || !history.pushState || !window.AbortController) {
    return; // plain navigation keeps working
  }
  window.__estacleNav = true;

  var SHELL = sidebar.getAttribute('data-shell');

  function childSidebar(root) {
    return Array.prototype.filter.call(root.children, function (c) {
      return c.tagName === 'ASIDE' && c.classList.contains('sidebar') && c.hasAttribute('data-shell');
    })[0] || null;
  }

  // The swappable content region: every element child of .app-layout except the sidebar
  // (and non-visual script/style nodes that the sidebar partial leaves in there).
  function contentOf(root, sidebarEl) {
    return Array.prototype.filter.call(root.children, function (c) {
      return c !== sidebarEl && !/^(SCRIPT|STYLE|NOSCRIPT|LINK|TEMPLATE)$/.test(c.tagName);
    });
  }
  var NO_AJAX_PREFIXES = ['/logout', '/static/', '/admin/export/', '/presence/'];
  var reducedMotion = window.matchMedia ? window.matchMedia('(prefers-reduced-motion: reduce)') : { matches: false };

  var navId = 0;            // identifies the latest navigation; older ones are discarded
  var controller = null;    // aborts the in-flight request when a newer one starts
  var pageListeners = [];   // document/window listeners registered by page scripts
  var loadedScripts = {};   // absolute src -> true (external scripts are loaded once)
  var lastLocation = location.pathname + location.search;
  var busyTimer = null;
  var errorTimer = null;

  var nativeSubmit = HTMLFormElement.prototype.submit;
  var protoAdd = EventTarget.prototype.addEventListener;
  var ready = false;        // DOM-dependent setup finished (see init())
  var ajaxRun = null;       // set while an inline script of a swapped-in page is executing

  // Record document/window listeners added synchronously by inline page scripts (both the
  // first page's, run by the browser, and later pages', run by us) so they can be removed
  // when that page is replaced. Library scripts (src=...) and the sidebar's presence
  // beacon are deliberately not recorded.
  function isPageScript(cs) {
    return !!cs && !cs.src && !cs.closest('aside.sidebar') &&
           (cs.textContent || '').indexOf('/presence/offline') === -1;
  }
  [document, window].forEach(function (t) {
    t.addEventListener = function (type, fn, opts) {
      // A swapped-in page is already loaded, so its "ready" handlers must be run by us.
      if (ajaxRun && ((t === document && type === 'DOMContentLoaded') || (t === window && type === 'load'))) {
        ajaxRun.ready.push(fn);
        return;
      }
      if (isPageScript(document.currentScript)) pageListeners.push({ target: t, type: type, fn: fn, opts: opts });
      return protoAdd.call(t, type, fn, opts);
    };
  });

  /* ------------------------------------------------------------------ *
   * Active state: ONE authoritative active link, derived in one place.
   * Dropdown expansion (.open) is independent of active (.has-active).
   * ------------------------------------------------------------------ */

  var state = { activePath: null };

  function navLinks() {
    return Array.prototype.slice.call(sidebar.querySelectorAll('a.nav-item, a.nav-subitem'));
  }

  function matchByUrl(pathname) {
    var best = null;
    navLinks().forEach(function (a) {
      var p = a.pathname.replace(/\/+$/, '') || '/';
      var path = pathname.replace(/\/+$/, '') || '/';
      var isRoot = p.split('/').filter(Boolean).length <= 1; // /admin, /client, /agent
      var hit = path === p || (!isRoot && path.indexOf(p + '/') === 0);
      if (hit && (!best || p.length > best.p.length)) best = { a: a, p: p };
    });
    return best ? best.a : null;
  }

  // Prefer what the server decided for that page (it already knows e.g. that
  // /client/property/3 belongs under "Browse"); fall back to URL matching for
  // nested routes the server leaves unmarked (e.g. /admin/properties/5).
  function resolveActive(sourceSidebar, pathname) {
    var marked = Array.prototype.slice.call(
      sourceSidebar.querySelectorAll('a.nav-item.active, a.nav-subitem.active'));
    var mine = navLinks();
    var candidates = marked.map(function (m) {
      return mine.filter(function (a) { return a.pathname === m.pathname; })[0];
    }).filter(Boolean);
    if (candidates.length === 1) return candidates[0];
    if (candidates.length > 1) {
      var byUrl = matchByUrl(pathname);
      return candidates.indexOf(byUrl) !== -1 ? byUrl : candidates[0];
    }
    return matchByUrl(pathname);
  }

  function applyActive(link) {
    navLinks().forEach(function (a) {
      var on = a === link;
      a.classList.toggle('active', on);
      if (on) a.setAttribute('aria-current', 'page'); else a.removeAttribute('aria-current');
    });
    Array.prototype.forEach.call(sidebar.querySelectorAll('.nav-dropdown'), function (d) {
      d.classList.toggle('has-active', !!link && d.contains(link));
    });
    if (link) {
      var parent = link.closest('.nav-dropdown');
      if (parent) parent.classList.add('open'); // reveal the active item; never collapses others
    }
    state.activePath = link ? link.pathname : null;
  }

  /* ------------------------------------------------------------------ *
   * Helpers
   * ------------------------------------------------------------------ */

  function sameOrigin(url) { return url.origin === location.origin; }

  function samePageHash(url) {
    return url.hash && url.pathname === location.pathname && url.search === location.search;
  }

  function excluded(url) {
    return NO_AJAX_PREFIXES.some(function (p) { return url.pathname.indexOf(p) === 0; });
  }

  function showBusy(on) {
    clearTimeout(busyTimer);
    if (on) {
      busyTimer = setTimeout(function () { document.documentElement.classList.add('nav-loading'); }, 120);
      layout.setAttribute('aria-busy', 'true');
    } else {
      document.documentElement.classList.remove('nav-loading');
      layout.removeAttribute('aria-busy');
    }
  }

  function showError(message) {
    var el = document.getElementById('estacle-nav-error');
    if (!el) {
      el = document.createElement('div');
      el.id = 'estacle-nav-error';
      el.setAttribute('role', 'alert');
      document.body.appendChild(el);
    }
    el.textContent = message;
    el.classList.add('show');
    clearTimeout(errorTimer);
    errorTimer = setTimeout(function () { el.classList.remove('show'); }, 6000);
  }

  function restartEnterAnimation() {
    if (reducedMotion.matches) return;
    var nodes = contentOf(layout, sidebar);
    nodes.forEach(function (n) { n.style.animation = 'none'; });
    void layout.offsetWidth; // reflow so the CSS animation starts from the beginning
    nodes.forEach(function (n) { n.style.animation = ''; });
  }

  function fullNavigate(url) {
    showBusy(false); // a download keeps this page alive, so never leave the busy state behind
    window.location.assign(url);
  }

  /* ------------------------------------------------------------------ *
   * Page-script handling
   * ------------------------------------------------------------------ */

  function teardownPage() {
    pageListeners.forEach(function (l) {
      try { l.target.removeEventListener(l.type, l.fn, l.opts); } catch (e) { /* ignore */ }
    });
    pageListeners = [];
  }

  function loadExternalScript(src, type) {
    return new Promise(function (resolve) {
      if (loadedScripts[src]) return resolve();
      var s = document.createElement('script');
      s.src = src;
      if (type) s.type = type;
      s.onload = function () { loadedScripts[src] = true; resolve(); };
      s.onerror = function () { console.error('[estacle-nav] failed to load script', src); resolve(); };
      document.head.appendChild(s);
    });
  }

  // Run an inline page script inside a block, so top-level const/let can be re-declared on every
  // visit. Listeners it adds are recorded by the permanent recorder installed above.
  function runInline(code) {
    ajaxRun = { ready: [] };
    var run = ajaxRun;
    try {
      var el = document.createElement('script');
      el.textContent = '{\n' + code + '\n}';
      document.body.appendChild(el);
      el.remove();
    } finally {
      ajaxRun = null;
    }
    run.ready.forEach(function (fn) {
      try {
        var ev = new Event('DOMContentLoaded');
        if (typeof fn === 'function') fn.call(document, ev); else if (fn && fn.handleEvent) fn.handleEvent(ev);
      } catch (e) { console.error(e); }
    });
  }

  function runScripts(scripts, id) {
    return scripts.reduce(function (chain, node) {
      return chain.then(function () {
        if (id !== navId) return;
        var type = (node.getAttribute('type') || '').toLowerCase();
        if (type && type !== 'text/javascript' && type !== 'application/javascript' && type !== 'module') return;
        var src = node.getAttribute('src');
        if (src) return loadExternalScript(new URL(src, location.href).href, type);
        runInline(node.textContent);
      });
    }, Promise.resolve());
  }

  function wantedScripts(doc) {
    return Array.prototype.slice.call(doc.querySelectorAll('script')).filter(function (s) {
      if (s.closest('aside.sidebar')) return false;
      var text = s.textContent || '';
      if (text.indexOf('/presence/offline') !== -1) return false; // handled once by the persistent shell
      if (/app-nav\.js/.test(s.getAttribute('src') || '')) return false;
      return true;
    });
  }

  /* ------------------------------------------------------------------ *
   * Swapping the page
   * ------------------------------------------------------------------ */

  function ensureStylesheets(doc) {
    var waits = [];
    Array.prototype.forEach.call(doc.querySelectorAll('link[rel~="stylesheet"][href]'), function (l) {
      var href = new URL(l.getAttribute('href'), location.href).href;
      var exists = Array.prototype.some.call(document.querySelectorAll('link[rel~="stylesheet"]'), function (e) { return e.href === href; });
      if (exists) return;
      waits.push(new Promise(function (resolve) {
        var n = document.createElement('link');
        n.rel = 'stylesheet';
        n.href = href;
        n.onload = n.onerror = function () { resolve(); };
        document.head.appendChild(n);
      }));
    });
    return Promise.all(waits);
  }

  function swapPage(doc, finalUrl, opts, id) {
    teardownPage();

    // page-specific <style> blocks: drop the old page's, add the new page's (same cascade order)
    Array.prototype.forEach.call(document.querySelectorAll('style[data-page-style]'), function (s) { s.remove(); });
    Array.prototype.forEach.call(doc.querySelectorAll('style'), function (s) {
      if (s.closest('aside.sidebar')) return;
      var copy = document.importNode(s, true);
      copy.setAttribute('data-page-style', '');
      document.head.appendChild(copy);
    });

    // body-level extras outside the layout (e.g. flash toasts)
    Array.prototype.forEach.call(document.querySelectorAll('[data-page-extra]'), function (n) { n.remove(); });
    Array.prototype.forEach.call(doc.body.children, function (el) {
      if (el.matches('.app-layout, script, style, noscript')) return;
      var copy = document.importNode(el, true);
      copy.setAttribute('data-page-extra', '');
      document.body.appendChild(copy);
    });

    document.body.className = doc.body.className;
    document.body.style.overflow = '';
    document.title = doc.title;

    // the content region: scripts/styles are handled separately, never injected as markup
    var newLayout = doc.querySelector('.app-layout');
    var fragment = document.createDocumentFragment();
    contentOf(newLayout, childSidebar(newLayout)).forEach(function (node) {
      var copy = document.importNode(node, true);
      Array.prototype.forEach.call(copy.querySelectorAll('script, style'), function (n) { n.remove(); });
      fragment.appendChild(copy);
    });
    contentOf(layout, sidebar).forEach(function (old) { old.remove(); });
    layout.appendChild(fragment);

    // history (final URL after any redirects), then active state, then scroll + animation
    var target = new URL(finalUrl);
    if (opts.history === 'push') {
      if (target.href === location.href) history.replaceState({ estacle: true }, '', target.href);
      else history.pushState({ estacle: true }, '', target.href);
    } else if (opts.history === 'replace') {
      history.replaceState({ estacle: true }, '', target.href);
    }
    lastLocation = location.pathname + location.search;

    applyActive(resolveActive(childSidebar(newLayout), target.pathname));

    if (opts.history === 'pop') window.scrollTo(0, opts.scrollY || 0);
    else if (target.hash && document.getElementById(decodeURIComponent(target.hash.slice(1)))) {
      document.getElementById(decodeURIComponent(target.hash.slice(1))).scrollIntoView();
    } else window.scrollTo(0, 0);

    restartEnterAnimation();

    var auto = layout.querySelector('[autofocus]');
    if (auto && typeof auto.focus === 'function') auto.focus({ preventScroll: true });

    return runScripts(wantedScripts(doc), id);
  }

  /* ------------------------------------------------------------------ *
   * Navigation
   * ------------------------------------------------------------------ */

  function navigate(url, opts) {
    opts = opts || {};
    var method = (opts.method || 'GET').toUpperCase();
    var id = ++navId;
    if (controller) controller.abort();
    controller = new AbortController();
    var signal = controller.signal;

    if (opts.history === 'push') {
      try { history.replaceState(Object.assign({}, history.state, { estacle: true, scrollY: window.scrollY }), ''); } catch (e) { /* ignore */ }
    }
    showBusy(true);

    var init = {
      method: method,
      credentials: 'same-origin',
      redirect: 'follow',
      signal: signal,
      headers: { 'X-Requested-With': 'estacle-nav', 'Accept': 'text/html,application/xhtml+xml' }
    };
    if (opts.body && method !== 'GET') init.body = opts.body;

    return fetch(url, init).then(function (resp) {
      if (id !== navId) return null;

      var type = (resp.headers.get('content-type') || '').toLowerCase();
      var isHtml = type.indexOf('text/html') !== -1 || type.indexOf('application/xhtml') !== -1;

      if (!isHtml) {
        // e.g. a CSV export: let the browser handle it natively. A POST must never be re-sent.
        if (method === 'GET') { fullNavigate(resp.url || url); return null; }
        showBusy(false);
        showError('The server sent an unexpected response. Please reload the page.');
        return null;
      }

      return resp.text().then(function (text) {
        if (id !== navId) return null;
        var doc = new DOMParser().parseFromString(text, 'text/html');
        var newLayout = doc.querySelector('.app-layout');
        var newSidebar = newLayout ? childSidebar(newLayout) : null;
        var usable = resp.ok && newSidebar && contentOf(newLayout, newSidebar).length &&
                     newSidebar.getAttribute('data-shell') === SHELL;

        if (!usable) {
          // different layout (login, error page, print view...): let the browser show it properly
          if (method === 'GET' || resp.redirected) { fullNavigate(resp.url || url); return null; }
          document.open(); document.write(text); document.close();
          return null;
        }

        return ensureStylesheets(doc).then(function () {
          if (id !== navId) return null;
          return swapPage(doc, resp.url || url, opts, id).then(function () {
            if (id === navId) showBusy(false);
          });
        });
      });
    }).catch(function (err) {
      if (err && err.name === 'AbortError') return;      // superseded by a newer navigation
      if (id !== navId) return;
      showBusy(false);
      console.error('[estacle-nav]', err);
      if (method === 'GET') {
        showError('Could not load the page - reloading normally...');
        setTimeout(function () { fullNavigate(url); }, 400);
      } else {
        showError('Could not reach the server. Your changes were not confirmed - please try again.');
      }
    });
  }

  /* ------------------------------------------------------------------ *
   * Event interception (delegated, registered exactly once)
   * ------------------------------------------------------------------ */

  protoAdd.call(document, 'click', function (e) {
    if (!ready || e.defaultPrevented || e.button !== 0 || e.metaKey || e.ctrlKey || e.shiftKey || e.altKey) return;
    var a = e.target && e.target.closest ? e.target.closest('a[href]') : null;
    if (!a) return;
    if (a.hasAttribute('download') || a.hasAttribute('data-no-ajax')) return;
    if (a.target && a.target !== '_self') return;
    if (!/^https?:$/.test(a.protocol)) return;
    if ((a.getAttribute('href') || '').charAt(0) === '#') return; // in-page anchors / href="#" buttons
    var url = new URL(a.href);
    if (!sameOrigin(url) || excluded(url) || samePageHash(url)) return;
    e.preventDefault();
    navigate(url.href, { history: 'push' });
  });

  protoAdd.call(document, 'submit', function (e) {
    if (!ready || e.defaultPrevented) return;
    var form = e.target;
    if (!(form instanceof HTMLFormElement)) return;
    if (form.hasAttribute('data-no-ajax') || (form.target && form.target !== '_self')) return;

    var submitter = e.submitter || null;
    var method = ((submitter && submitter.getAttribute('formmethod')) || form.getAttribute('method') || 'get').toLowerCase();
    var action = (submitter && submitter.getAttribute('formaction')) || form.getAttribute('action') || location.href;
    var enctype = ((submitter && submitter.getAttribute('formenctype')) || form.getAttribute('enctype') || 'application/x-www-form-urlencoded').toLowerCase();
    if (method !== 'get' && method !== 'post') return;
    if (enctype === 'text/plain') return;

    var url;
    var data;
    try {
      url = new URL(action, location.href);
      data = submitter ? new FormData(form, submitter) : new FormData(form);
    } catch (err) {
      return; // browser too old for this: native submit
    }
    if (!sameOrigin(url) || excluded(url)) return;

    e.preventDefault();
    if (method === 'get') {
      var params = new URLSearchParams();
      data.forEach(function (v, k) { if (typeof v === 'string') params.append(k, v); });
      url.search = params.toString();
      navigate(url.href, { history: 'push' });
    } else {
      var body = enctype === 'multipart/form-data' ? data : (function () {
        var p = new URLSearchParams();
        data.forEach(function (v, k) { p.append(k, typeof v === 'string' ? v : v.name); });
        return p;
      })();
      navigate(url.href, { method: 'POST', body: body, history: 'push' });
    }
  });

  // form.submit() (used by onchange="this.form.submit()") skips the submit event; route it
  // through one so those forms are handled too. Anything we do not take over submits natively.
  HTMLFormElement.prototype.submit = function () {
    var ev = new Event('submit', { bubbles: true, cancelable: true });
    if (this.dispatchEvent(ev)) nativeSubmit.call(this);
  };

  protoAdd.call(window, 'popstate', function (e) {
    if (!ready) return;
    var now = location.pathname + location.search;
    if (now === lastLocation) return; // hash-only change: browser handles the jump
    navigate(location.href, { history: 'pop', scrollY: e.state && e.state.scrollY });
  });

  /* ------------------------------------------------------------------ *
   * Initial load (DOM-dependent setup; the listeners above are already in place)
   * ------------------------------------------------------------------ */

  function init() {
    if ('scrollRestoration' in history) history.scrollRestoration = 'manual';
    Array.prototype.forEach.call(document.querySelectorAll('style'), function (st) {
      if (!st.closest('aside.sidebar')) st.setAttribute('data-page-style', '');
    });
    Array.prototype.forEach.call(document.body.children, function (el) {
      if (!el.matches('.app-layout, script, style, noscript')) el.setAttribute('data-page-extra', '');
    });
    Array.prototype.forEach.call(document.querySelectorAll('script[src]'), function (sc) { loadedScripts[sc.src] = true; });
    history.replaceState(Object.assign({}, history.state, { estacle: true }), '');
    lastLocation = location.pathname + location.search;
    applyActive(resolveActive(sidebar, location.pathname)); // recompute on every full load too
    ready = true;
  }

  if (document.readyState === 'loading') protoAdd.call(document, 'DOMContentLoaded', init);
  else init();
})();
