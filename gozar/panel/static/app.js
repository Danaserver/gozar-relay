/* Gozar admin panel — vanilla JS single-page app (no build step). */
(function () {
  'use strict';

  var G = window.GOZAR;
  var S = { state: null, view: (location.hash || '#overview').slice(1), logs: [], logFilter: { service: '', key_id: '', errors: false } };

  // ------------------------------------------------------------------ utils
  function esc(v) {
    return String(v == null ? '' : v).replace(/[&<>"']/g, function (c) {
      return { '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[c];
    });
  }
  function fa(n) { return Number(n || 0).toLocaleString('fa-IR'); }
  function bytes(n) {
    n = Number(n || 0);
    var u = ['B', 'KB', 'MB', 'GB', 'TB'], i = 0;
    while (n >= 1024 && i < u.length - 1) { n /= 1024; i++; }
    return '<bdi dir="ltr">' + (i ? n.toFixed(1) : n) + ' ' + u[i] + '</bdi>';
  }
  function ago(ts) {
    if (!ts) return 'هرگز';
    var d = Date.now() / 1000 - ts;
    if (d < 60) return 'لحظاتی پیش';
    if (d < 3600) return fa(Math.floor(d / 60)) + ' دقیقه پیش';
    if (d < 86400) return fa(Math.floor(d / 3600)) + ' ساعت پیش';
    return fa(Math.floor(d / 86400)) + ' روز پیش';
  }
  function dateStr(ts) { return ts ? new Date(ts * 1000).toLocaleString('fa-IR', { dateStyle: 'medium', timeStyle: 'short' }) : '—'; }
  function $(sel, root) { return (root || document).querySelector(sel); }
  function $$(sel, root) { return Array.prototype.slice.call((root || document).querySelectorAll(sel)); }

  function toast(msg, err) {
    var t = document.createElement('div');
    t.className = 'toast' + (err ? ' err' : '');
    t.textContent = msg;
    $('#toasts').appendChild(t);
    setTimeout(function () { t.remove(); }, 3200);
  }

  function copy(text) {
    function fallback() {
      var ta = document.createElement('textarea');
      ta.value = text; ta.style.position = 'fixed'; ta.style.opacity = '0';
      document.body.appendChild(ta); ta.select();
      try { document.execCommand('copy'); toast('کپی شد'); } catch (e) { prompt('کپی کنید:', text); }
      ta.remove();
    }
    if (navigator.clipboard && window.isSecureContext) {
      navigator.clipboard.writeText(text).then(function () { toast('کپی شد'); }, fallback);
    } else fallback();
  }

  function api(path, data) {
    var opt = { credentials: 'same-origin', headers: {} };
    if (data !== undefined) {
      opt.method = 'POST';
      opt.headers['Content-Type'] = 'application/json';
      opt.headers['X-CSRF-Token'] = G.csrf;
      opt.body = JSON.stringify(data);
    }
    return fetch(G.base + '/_panel/api/' + path, opt).then(function (r) {
      if (r.status === 401) { location.reload(); throw new Error('unauthorized'); }
      return r.json().then(function (j) {
        if (!r.ok) throw new Error(j.error || ('HTTP ' + r.status));
        return j;
      });
    });
  }

  function load() {
    return api('state').then(function (st) { S.state = st; render(); });
  }

  // ------------------------------------------------------------------ icons
  var I = {
    overview: '<path d="M3 13h8V3H3zM13 21h8V11h-8zM3 21h8v-6H3zM13 3v6h8V3z"/>',
    services: '<rect x="3" y="3" width="18" height="6" rx="2"/><rect x="3" y="15" width="18" height="6" rx="2"/><path d="M7 6h.01M7 18h.01"/>',
    keys: '<circle cx="7.5" cy="15.5" r="4.5"/><path d="m21 2-9.6 9.6M15.5 7.5l3 3L22 7l-3-3"/>',
    logs: '<path d="M4 6h16M4 12h16M4 18h10"/>',
    guide: '<path d="M4 19.5A2.5 2.5 0 0 1 6.5 17H20V3H6.5A2.5 2.5 0 0 0 4 5.5z"/><path d="M8 7h8M8 11h6"/>',
    settings: '<circle cx="12" cy="12" r="3"/><path d="M19.4 15a1.65 1.65 0 0 0 .33 1.82l.06.06a2 2 0 1 1-2.83 2.83l-.06-.06a1.65 1.65 0 0 0-1.82-.33 1.65 1.65 0 0 0-1 1.51V21a2 2 0 1 1-4 0v-.09A1.65 1.65 0 0 0 9 19.4a1.65 1.65 0 0 0-1.82.33l-.06.06a2 2 0 1 1-2.83-2.83l.06-.06A1.65 1.65 0 0 0 4.6 15a1.65 1.65 0 0 0-1.51-1H3a2 2 0 1 1 0-4h.09A1.65 1.65 0 0 0 4.6 9a1.65 1.65 0 0 0-.33-1.82l-.06-.06a2 2 0 1 1 2.83-2.83l.06.06A1.65 1.65 0 0 0 9 4.6a1.65 1.65 0 0 0 1-1.51V3a2 2 0 1 1 4 0v.09a1.65 1.65 0 0 0 1 1.51 1.65 1.65 0 0 0 1.82-.33l.06-.06a2 2 0 1 1 2.83 2.83l-.06.06A1.65 1.65 0 0 0 19.4 9a1.65 1.65 0 0 0 1.51 1H21a2 2 0 1 1 0 4h-.09a1.65 1.65 0 0 0-1.51 1z"/>',
    plus: '<path d="M12 5v14M5 12h14"/>',
    edit: '<path d="M12 20h9M16.5 3.5a2.1 2.1 0 1 1 3 3L7 19l-4 1 1-4z"/>',
    trash: '<path d="M3 6h18M8 6V4h8v2M19 6l-1 14H6L5 6"/>',
    code: '<path d="m16 18 6-6-6-6M8 6l-6 6 6 6"/>',
    bolt: '<path d="M13 2 3 14h9l-1 8 10-12h-9z"/>',
    refresh: '<path d="M21 12a9 9 0 1 1-3-6.7L21 8M21 3v5h-5"/>',
    copy: '<rect x="9" y="9" width="13" height="13" rx="2"/><path d="M5 15H4a2 2 0 0 1-2-2V4a2 2 0 0 1 2-2h9a2 2 0 0 1 2 2v1"/>',
    logout: '<path d="M9 21H5a2 2 0 0 1-2-2V5a2 2 0 0 1 2-2h4M16 17l5-5-5-5M21 12H9"/>',
    power: '<path d="M18.36 6.64a9 9 0 1 1-12.73 0M12 2v10"/>',
    x: '<path d="M18 6 6 18M6 6l12 12"/>',
    lock: '<rect x="3" y="11" width="18" height="11" rx="2"/><path d="M7 11V7a5 5 0 0 1 10 0v4"/>'
  };
  function icon(n) { return '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">' + (I[n] || '') + '</svg>'; }

  var BRAND = {
    telegram: '<svg viewBox="0 0 24 24"><circle cx="12" cy="12" r="11" fill="#229ED9"/><path d="m5.5 11.7 11-4.3c.5-.2 1 .1.8.9l-1.9 8.8c-.1.6-.5.8-1 .5l-2.9-2.1-1.4 1.3c-.2.2-.3.3-.6.3l.2-2.9 5.3-4.8c.2-.2 0-.3-.4-.1l-6.5 4.1-2.8-.9c-.6-.2-.6-.6.2-.8z" fill="#fff"/></svg>',
    openrouter: '<svg viewBox="0 0 24 24" fill="none" stroke="#a5b4fc" stroke-width="2" stroke-linecap="round"><path d="M3 12h5c3 0 4-6 7-6h6M15 18h6M3 12h5c3 0 4 6 7 6"/><path d="m18 3 3 3-3 3M18 15l3 3-3 3"/></svg>',
    gemini: '<svg viewBox="0 0 24 24"><defs><linearGradient id="gm" x1="0" y1="0" x2="1" y2="1"><stop offset="0" stop-color="#4285f4"/><stop offset="1" stop-color="#d96570"/></linearGradient></defs><path d="M12 2c.6 5.3 4.7 9.4 10 10-5.3.6-9.4 4.7-10 10-.6-5.3-4.7-9.4-10-10 5.3-.6 9.4-4.7 10-10z" fill="url(#gm)"/></svg>',
    openai: '<svg viewBox="0 0 24 24" fill="none" stroke="#e5e7eb" stroke-width="1.7"><path d="M12 3.5 19.4 7.8v8.4L12 20.5 4.6 16.2V7.8z"/><path d="M12 3.5v8.5l7.4 4.2M12 12l-7.4 4.2"/></svg>',
    anthropic: '<svg viewBox="0 0 24 24"><path d="M13.8 4h3.3L23 20h-3.3zM7 4h3.4l5.9 16h-3.3l-1.2-3.4H5.6L4.4 20H1zm-.3 9.7h4.1L8.7 8z" fill="#d97757"/></svg>',
    groq: '<svg viewBox="0 0 24 24"><circle cx="12" cy="12" r="10" fill="#f55036"/><path d="M12 7a5 5 0 1 0 0 10h2v-4h-2" fill="none" stroke="#fff" stroke-width="2"/></svg>',
    github: '<svg viewBox="0 0 24 24"><path fill="#e5e7eb" d="M12 1.5a10.5 10.5 0 0 0-3.3 20.5c.5.1.7-.2.7-.5v-1.8c-2.9.6-3.5-1.4-3.5-1.4-.5-1.2-1.2-1.5-1.2-1.5-.9-.7.1-.6.1-.6 1 .1 1.6 1.1 1.6 1.1.9 1.6 2.5 1.1 3.1.9.1-.7.4-1.1.7-1.4-2.3-.3-4.8-1.2-4.8-5.2 0-1.1.4-2.1 1.1-2.8-.1-.3-.5-1.4.1-2.8 0 0 .9-.3 2.9 1.1a10 10 0 0 1 5.2 0c2-1.4 2.9-1.1 2.9-1.1.6 1.4.2 2.5.1 2.8.7.7 1.1 1.7 1.1 2.8 0 4-2.5 4.9-4.8 5.2.4.3.7 1 .7 2v3c0 .3.2.6.7.5A10.5 10.5 0 0 0 12 1.5z"/></svg>',
    custom: '<svg viewBox="0 0 24 24" fill="none" stroke="#22d3ee" stroke-width="2" stroke-linecap="round"><circle cx="12" cy="12" r="9"/><path d="M3 12h18M12 3a14 14 0 0 1 0 18M12 3a14 14 0 0 0 0 18"/></svg>'
  };
  function brand(p) { return BRAND[p] || BRAND.custom; }

  // -------------------------------------------------------------- snippets
  var OPENAI_PATH = { openrouter: '/api/v1', openai: '/v1', groq: '/openai/v1' };
  var DEMO_MODEL = { openrouter: 'openai/gpt-4o-mini', openai: 'gpt-4o-mini', groq: 'llama-3.3-70b-versatile' };

  function snippets(svc, key) {
    var base = S.state.base_url, K = key ? key.key : 'YOUR_ACCESS_KEY', s = svc.slug, p = svc.preset, out = [];
    var keyed = base + '/' + K + '/' + s;          // key embedded in the path
    var plain = base + '/' + s;                     // key sent as a credential
    var managed = svc.managed;

    if (p === 'telegram') {
      out.push({ t: 'آدرس پایه', c: keyed + '/bot<BOT_TOKEN>/getMe\n\n# Files:\n' + keyed + '/file/bot<BOT_TOKEN>/<file_path>' });
      out.push({ t: 'requests', c: 'import requests\n\nAPI = "' + keyed + '/bot" + BOT_TOKEN\nrequests.post(f"{API}/sendMessage", json={"chat_id": 123, "text": "سلام از ایران"})' });
      out.push({ t: 'python-telegram-bot', c: 'from telegram.ext import ApplicationBuilder\n\napp = (\n    ApplicationBuilder()\n    .token(BOT_TOKEN)\n    .base_url("' + keyed + '/bot")\n    .base_file_url("' + keyed + '/file/bot")\n    .build()\n)' });
      out.push({ t: 'aiogram 3', c: 'from aiogram import Bot\nfrom aiogram.client.session.aiohttp import AiohttpSession\nfrom aiogram.client.telegram import TelegramAPIServer\n\nsession = AiohttpSession(api=TelegramAPIServer.from_base("' + keyed + '"))\nbot = Bot(BOT_TOKEN, session=session)' });
      out.push({ t: 'telebot', c: 'import telebot\nfrom telebot import apihelper\n\napihelper.API_URL = "' + keyed + '/bot{0}/{1}"\napihelper.FILE_URL = "' + keyed + '/file/bot{0}/{1}"\nbot = telebot.TeleBot(BOT_TOKEN)' });
      out.push({ t: 'PHP', c: '<?php\n$api = "' + keyed + '/bot" . $botToken;\nfile_get_contents("$api/sendMessage?" . http_build_query(["chat_id" => 123, "text" => "سلام"]));' });
      return out;
    }
    if (OPENAI_PATH[p]) {
      var path = OPENAI_PATH[p], model = DEMO_MODEL[p];
      var url = managed ? plain + path : keyed + path, ak = managed ? K : 'YOUR_' + p.toUpperCase() + '_API_KEY';
      out.push({ t: 'Python (openai)', c: 'from openai import OpenAI\n\nclient = OpenAI(\n    base_url="' + url + '",\n    api_key="' + ak + '",\n)\nr = client.chat.completions.create(\n    model="' + model + '",\n    messages=[{"role": "user", "content": "سلام!"}],\n)\nprint(r.choices[0].message.content)' });
      out.push({ t: 'Node.js', c: 'import OpenAI from "openai";\n\nconst client = new OpenAI({\n  baseURL: "' + url + '",\n  apiKey: "' + ak + '",\n});\nconst r = await client.chat.completions.create({\n  model: "' + model + '",\n  messages: [{ role: "user", content: "سلام!" }],\n});' });
      out.push({ t: 'cURL', c: 'curl ' + url + '/chat/completions \\\n  -H "Authorization: Bearer ' + ak + '" \\\n  -H "Content-Type: application/json" \\\n  -d \'{"model":"' + model + '","messages":[{"role":"user","content":"سلام"}]}\'' });
      out.push({ t: 'PHP', c: '<?php\n$ch = curl_init("' + url + '/chat/completions");\ncurl_setopt_array($ch, [\n  CURLOPT_RETURNTRANSFER => true,\n  CURLOPT_POST => true,\n  CURLOPT_HTTPHEADER => ["Authorization: Bearer ' + ak + '", "Content-Type: application/json"],\n  CURLOPT_POSTFIELDS => json_encode(["model" => "' + model + '", "messages" => [["role" => "user", "content" => "سلام"]]]),\n]);\necho curl_exec($ch);' });
      return out;
    }
    if (p === 'gemini') {
      var gurl = managed ? plain : keyed, gk = managed ? K : 'YOUR_GEMINI_API_KEY';
      out.push({ t: 'Python (google-genai)', c: 'from google import genai\nfrom google.genai import types\n\nclient = genai.Client(\n    api_key="' + gk + '",\n    http_options=types.HttpOptions(base_url="' + gurl + '"),\n)\nr = client.models.generate_content(model="gemini-2.5-flash", contents="سلام!")\nprint(r.text)' });
      out.push({ t: 'cURL', c: 'curl "' + gurl + '/v1beta/models/gemini-2.5-flash:generateContent" \\\n  -H "x-goog-api-key: ' + gk + '" \\\n  -H "Content-Type: application/json" \\\n  -d \'{"contents":[{"parts":[{"text":"سلام"}]}]}\'' });
      out.push({ t: 'OpenAI-compatible', c: 'from openai import OpenAI\n\nclient = OpenAI(base_url="' + gurl + '/v1beta/openai/", api_key="' + gk + '")\nclient.chat.completions.create(model="gemini-2.5-flash", messages=[{"role": "user", "content": "سلام"}])' });
      return out;
    }
    if (p === 'anthropic') {
      var aurl = managed ? plain : keyed, akk = managed ? K : 'YOUR_ANTHROPIC_API_KEY';
      out.push({ t: 'Python (anthropic)', c: 'import anthropic\n\nclient = anthropic.Anthropic(base_url="' + aurl + '", api_key="' + akk + '")\nmsg = client.messages.create(\n    model="claude-sonnet-4-5", max_tokens=512,\n    messages=[{"role": "user", "content": "سلام!"}],\n)' });
      out.push({ t: 'cURL', c: 'curl ' + aurl + '/v1/messages \\\n  -H "x-api-key: ' + akk + '" -H "anthropic-version: 2023-06-01" \\\n  -H "content-type: application/json" \\\n  -d \'{"model":"claude-sonnet-4-5","max_tokens":256,"messages":[{"role":"user","content":"سلام"}]}\'' });
      return out;
    }
    out.push({ t: 'آدرس', c: '# Everything after the slug is forwarded to ' + svc.upstream + '\n' + keyed + '/<path>\n\n# or send the key in a header:\n' + plain + '/<path>\nX-Relay-Key: ' + K });
    out.push({ t: 'cURL', c: 'curl ' + plain + '/ \\\n  -H "X-Relay-Key: ' + K + '"' });
    out.push({ t: 'Python', c: 'import requests\n\nr = requests.get("' + plain + '/", headers={"X-Relay-Key": "' + K + '"})\nprint(r.status_code, r.text[:200])' });
    return out;
  }

  function codeBlock(code) {
    return '<div class="code-box"><pre class="code">' + esc(code) + '</pre>' +
      '<button class="btn btn-sm copy" data-copy="' + esc(code) + '">' + icon('copy') + 'کپی</button></div>';
  }

  function snippetTabs(svc, key) {
    var list = snippets(svc, key);
    var tabs = list.map(function (s, i) { return '<div class="tab' + (i ? '' : ' active') + '" data-tab="' + i + '">' + esc(s.t) + '</div>'; }).join('');
    var panes = list.map(function (s, i) { return '<div class="pane" data-pane="' + i + '"' + (i ? ' hidden' : '') + '>' + codeBlock(s.c) + '</div>'; }).join('');
    return '<div class="tabs">' + tabs + '</div>' + panes;
  }

  // ------------------------------------------------------------------ views
  var VIEWS = [
    ['overview', 'داشبورد'], ['services', 'سرویس‌ها'], ['keys', 'کلیدهای دسترسی'],
    ['logs', 'گزارش درخواست‌ها'], ['guide', 'راهنمای اتصال'], ['settings', 'تنظیمات']
  ];

  function render() {
    if (!S.state) return;
    if (!VIEWS.some(function (v) { return v[0] === S.view; })) S.view = 'overview';
    var nav = VIEWS.map(function (v) {
      return '<div class="nav-item' + (S.view === v[0] ? ' active' : '') + '" data-nav="' + v[0] + '">' + icon(v[0]) + '<span>' + v[1] + '</span></div>';
    }).join('');
    var title = VIEWS.filter(function (v) { return v[0] === S.view; })[0][1];
    $('#app').innerHTML =
      '<div class="shell">' +
      '<aside class="sidebar"><div class="brand"><div class="brand-logo"><svg viewBox="0 0 24 24" fill="none" stroke="#fff" stroke-width="2.2" stroke-linecap="round" stroke-linejoin="round"><path d="M3 12h4l3-8 4 16 3-8h4"/></svg></div><div><b>گذر</b><span>Gozar Universal Relay</span></div></div>' + nav +
      '<div class="sidebar-foot"><div class="row"><span>' + esc(S.state.settings.admin_username) + '</span><span class="spacer"></span>' +
      '<form method="post" action="' + esc(G.base) + '/_panel/logout"><button class="btn btn-sm btn-ghost" title="خروج">' + icon('logout') + '</button></form></div>' +
      '<div>v' + esc(S.state.version) + '</div></div></aside>' +
      '<main class="main"><div class="topbar"><div><h1>' + title + '</h1><p class="mono">' + esc(S.state.base_url) + '</p></div><div class="top-actions" id="top-actions"></div></div>' +
      '<div id="view"></div></main>' +
      '<nav class="mobile-nav">' + nav + '</nav></div>';
    ({ overview: vOverview, services: vServices, keys: vKeys, logs: vLogs, guide: vGuide, settings: vSettings })[S.view]();
  }

  function vOverview() {
    var st = S.state, s = st.stats, on = st.settings.enabled;
    var max = Math.max.apply(null, s.hourly.map(function (h) { return h.n; }).concat([1]));
    var bars = s.hourly.map(function (h, i) {
      var t = new Date((s.hour_start + i * 3600) * 1000);
      return '<div class="bar" style="height:' + Math.max(2, h.n / max * 100) + '%" title="' + t.getHours() + ':00 — ' + h.n + ' req, ' + h.e + ' err">' +
        (h.e ? '<div class="e" style="height:' + (h.e / Math.max(h.n, 1) * 100) + '%"></div>' : '') + '</div>';
    }).join('');
    var bySvc = s.by_service.length ? s.by_service.map(function (r) {
      var svc = st.services.filter(function (x) { return x.slug === r.service; })[0];
      return '<tr><td><div class="row"><span class="svc-icon" style="width:30px;height:30px;border-radius:9px">' + brand(svc ? svc.preset : 'custom') + '</span>' + esc(svc ? svc.name : (r.service || 'نامشخص')) + '</div></td>' +
        '<td>' + fa(r.n) + '</td><td>' + (r.errors ? '<span class="badge b-err">' + fa(r.errors) + '</span>' : '<span class="badge b-ok">۰</span>') + '</td></tr>';
    }).join('') : '<tr><td colspan="3" class="empty">هنوز درخواستی ثبت نشده است</td></tr>';

    $('#view').innerHTML =
      '<div class="hero' + (on ? '' : ' off') + '"><div><h3><span class="pulse"></span>' + (on ? 'رله فعال است و درخواست‌ها را منتقل می‌کند' : 'رله خاموش است — همهٔ درخواست‌ها رد می‌شوند') + '</h3>' +
      '<p>' + fa(st.services.filter(function (x) { return x.enabled; }).length) + ' سرویس فعال · ' + fa(st.keys.filter(function (x) { return x.enabled; }).length) + ' کلید فعال</p></div>' +
      '<button class="btn ' + (on ? 'btn-danger' : 'btn-ok') + '" data-act="toggle-relay">' + icon('power') + (on ? 'خاموش کردن رله' : 'روشن کردن رله') + '</button></div>' +
      '<div class="grid grid-4">' +
      stat('درخواست‌ها (۲۴ ساعت)', fa(s.requests_24h), '', 'rgba(99,102,241,.3)') +
      stat('خطاها', fa(s.errors_24h), s.requests_24h ? fa(Math.round(s.errors_24h / s.requests_24h * 100)) + '٪ از کل' : '', 'rgba(239,68,68,.25)') +
      stat('میانگین پاسخ', '<bdi dir="ltr">' + fa(s.avg_ms) + ' ms</bdi>', 'درخواست‌های موفق', 'rgba(34,211,238,.25)') +
      stat('حجم منتقل‌شده', bytes(s.bytes_24h), 'پاسخ‌های ارسالی', 'rgba(16,185,129,.25)') + '</div>' +
      '<div class="grid grid-2" style="margin-top:18px"><div class="card"><div class="card-head"><h2>ترافیک ۲۴ ساعت اخیر</h2><span class="small dim">قرمز = خطا</span></div>' +
      '<div class="chart">' + bars + '</div><div class="chart-axis"><span>۲۴ ساعت پیش</span><span>اکنون</span></div></div>' +
      '<div class="card"><div class="card-head"><h2>به تفکیک سرویس</h2></div><div class="table-wrap"><table><thead><tr><th>سرویس</th><th>درخواست</th><th>خطا</th></tr></thead><tbody>' + bySvc + '</tbody></table></div></div></div>' +
      '<div class="card" style="margin-top:18px"><div class="card-head"><div><h2>وضعیت اتصال به سرویس‌ها</h2><p>بررسی دسترسی سرور رله به مقصدها</p></div><button class="btn btn-sm" data-act="test-all">' + icon('refresh') + 'بررسی همه</button></div>' +
      '<div class="svc-meta" id="health">' + st.services.map(function (x) {
        return '<span class="badge b-mute" data-health="' + x.id + '"><span class="status-dot"></span>' + esc(x.name) + '</span>';
      }).join('') + '</div></div>';
    testAll();
  }

  function stat(label, value, sub, glow) {
    return '<div class="card stat" style="--glow:' + glow + '"><div class="label">' + label + '</div><div class="value">' + value + '</div><div class="sub">' + (sub || '&nbsp;') + '</div></div>';
  }

  function testAll() {
    S.state.services.forEach(function (x) {
      var el = $('[data-health="' + x.id + '"]');
      if (!el) return;
      api('services/test', { id: x.id }).then(function (r) {
        el.className = 'badge ' + (r.ok ? 'b-ok' : 'b-err');
        el.title = r.detail;
        el.innerHTML = '<span class="status-dot ' + (r.ok ? 'ok' : 'err') + '"></span>' + esc(x.name) + ' · ' + (r.ok ? fa(r.ms) + 'ms' : 'خطا');
      }).catch(function () {});
    });
  }

  function vServices() {
    $('#top-actions').innerHTML = '<button class="btn btn-primary" data-act="add-service">' + icon('plus') + 'افزودن سرویس</button>';
    var st = S.state;
    if (!st.services.length) {
      $('#view').innerHTML = '<div class="card empty">' + icon('services') + '<p>هنوز سرویسی تعریف نشده است.</p></div>';
      return;
    }
    $('#view').innerHTML = '<div class="svc-grid">' + st.services.map(function (s) {
      var mode = s.managed ? '<span class="badge b-info">' + icon('lock') + ' کلید مدیریت‌شده (' + fa(s.upstream_keys.length) + ')</span>' : '<span class="badge b-mute">عبوری (کلید کاربر)</span>';
      return '<div class="card svc"><div class="svc-top"><div class="svc-icon">' + brand(s.preset) + '</div><div class="svc-title"><b>' + esc(s.name) + '</b><code>/' + esc(s.slug) + '</code></div>' +
        (s.enabled ? '<span class="badge b-ok">فعال</span>' : '<span class="badge b-err">غیرفعال</span>') + '</div>' +
        '<div class="svc-url">' + esc(s.upstream) + '</div>' +
        '<div class="svc-meta">' + mode + '<span class="badge b-mute">timeout ' + fa(s.timeout) + 's</span>' + (s.cors ? '<span class="badge b-warn">CORS</span>' : '') +
        '<span class="badge b-mute" data-health="' + s.id + '">…</span></div>' +
        (s.note ? '<div class="small muted">' + esc(s.note) + '</div>' : '') +
        '<div class="svc-actions"><button class="btn btn-sm" data-act="snip-service" data-id="' + s.id + '">' + icon('code') + 'کد اتصال</button>' +
        '<button class="btn btn-sm" data-act="edit-service" data-id="' + s.id + '">' + icon('edit') + 'ویرایش</button>' +
        '<button class="btn btn-sm" data-act="test-service" data-id="' + s.id + '">' + icon('bolt') + 'تست</button>' +
        '<span class="spacer"></span><button class="btn btn-sm btn-danger btn-icon" data-act="del-service" data-id="' + s.id + '" title="حذف">' + icon('trash') + '</button></div></div>';
    }).join('') + '</div>';
    testAll();
  }

  function keyServices(k) {
    if (k.services.indexOf('*') >= 0) return '<span class="badge b-info">همهٔ سرویس‌ها</span>';
    return k.services.map(function (sl) { return '<span class="badge b-mute">' + esc(sl) + '</span>'; }).join(' ');
  }

  function vKeys() {
    $('#top-actions').innerHTML = '<button class="btn btn-primary" data-act="add-key">' + icon('plus') + 'کلید جدید</button>';
    var keys = S.state.keys;
    var rows = keys.length ? keys.map(function (k) {
      var expired = k.expires_at && k.expires_at < Date.now() / 1000;
      var status = !k.enabled ? '<span class="badge b-err">غیرفعال</span>' : expired ? '<span class="badge b-warn">منقضی</span>' : '<span class="badge b-ok">فعال</span>';
      return '<tr><td><b>' + esc(k.name) + '</b>' + (k.note ? '<div class="small dim">' + esc(k.note) + '</div>' : '') + '</td>' +
        '<td><span class="key-pill">' + esc(k.key) + '<button data-copy="' + esc(k.key) + '">کپی</button></span></td>' +
        '<td>' + keyServices(k) + '</td>' +
        '<td class="small">' + fa(k.request_count) + '<div class="dim">' + ago(k.last_used_at) + '</div></td>' +
        '<td class="small">' + (k.rate_limit ? fa(k.rate_limit) + '/دقیقه' : '∞') + (k.expires_at ? '<div class="dim">تا ' + dateStr(k.expires_at) + '</div>' : '') + '</td>' +
        '<td>' + status + '</td>' +
        '<td><div class="row" style="flex-wrap:nowrap;gap:6px"><button class="btn btn-sm" data-act="snip-key" data-id="' + k.id + '">' + icon('code') + '</button>' +
        '<button class="btn btn-sm" data-act="edit-key" data-id="' + k.id + '">' + icon('edit') + '</button>' +
        '<button class="btn btn-sm" data-act="toggle-key" data-id="' + k.id + '">' + (k.enabled ? 'توقف' : 'فعال‌سازی') + '</button>' +
        '<button class="btn btn-sm btn-danger" data-act="del-key" data-id="' + k.id + '">' + icon('trash') + '</button></div></td></tr>';
    }).join('') : '<tr><td colspan="7" class="empty">هیچ کلیدی وجود ندارد. یک کلید بسازید.</td></tr>';
    $('#view').innerHTML = '<div class="card"><div class="card-head"><div><h2>کلیدهای دسترسی</h2><p>هر برنامه یا ربات یک کلید جدا داشته باشد تا بتوانید مصرفش را ببینید و در صورت نیاز قطعش کنید.</p></div></div>' +
      '<div class="table-wrap"><table><thead><tr><th>نام</th><th>کلید</th><th>سرویس‌های مجاز</th><th>مصرف</th><th>محدودیت</th><th>وضعیت</th><th></th></tr></thead><tbody>' + rows + '</tbody></table></div></div>';
  }

  function vLogs() {
    var st = S.state, f = S.logFilter;
    $('#top-actions').innerHTML = '<button class="btn btn-sm" data-act="reload-logs">' + icon('refresh') + 'بروزرسانی</button><button class="btn btn-sm btn-danger" data-act="clear-logs">' + icon('trash') + 'پاک کردن</button>';
    $('#view').innerHTML = '<div class="card"><div class="row" style="margin-bottom:14px">' +
      '<select id="lf-service" style="width:auto"><option value="">همهٔ سرویس‌ها</option>' + st.services.map(function (s) { return '<option value="' + esc(s.slug) + '"' + (f.service === s.slug ? ' selected' : '') + '>' + esc(s.name) + '</option>'; }).join('') + '</select>' +
      '<select id="lf-key" style="width:auto"><option value="">همهٔ کلیدها</option>' + st.keys.map(function (k) { return '<option value="' + k.id + '"' + (String(f.key_id) === String(k.id) ? ' selected' : '') + '>' + esc(k.name) + '</option>'; }).join('') + '</select>' +
      '<label class="switch"><input type="checkbox" id="lf-err"' + (f.errors ? ' checked' : '') + '><span class="track"></span>فقط خطاها</label></div>' +
      '<div class="table-wrap"><table><thead><tr><th>زمان</th><th>سرویس</th><th>کلید</th><th>درخواست</th><th>وضعیت</th><th>زمان پاسخ</th><th>حجم</th><th>IP</th></tr></thead><tbody id="log-rows"><tr><td colspan="8" class="empty"><span class="spinner"></span></td></tr></tbody></table></div></div>';
    loadLogs();
  }

  function loadLogs() {
    var f = S.logFilter;
    api('logs?service=' + encodeURIComponent(f.service) + '&key_id=' + encodeURIComponent(f.key_id) + '&errors=' + (f.errors ? 1 : 0)).then(function (r) {
      var el = $('#log-rows');
      if (!el) return;
      el.innerHTML = r.logs.length ? r.logs.map(function (l) {
        var cls = !l.status || l.status >= 500 ? 'b-err' : l.status >= 400 ? 'b-warn' : 'b-ok';
        return '<tr><td class="small" title="' + esc(dateStr(l.ts)) + '">' + ago(l.ts) + '</td><td>' + esc(l.service || '—') + '</td><td class="small">' + esc(l.key_name || '—') + '</td>' +
          '<td class="mono small" style="max-width:340px;overflow:hidden;text-overflow:ellipsis;white-space:nowrap" title="' + esc(l.path) + (l.error ? '\n' + esc(l.error) : '') + '"><b>' + esc(l.method) + '</b> ' + esc(l.path) + '</td>' +
          '<td><span class="badge ' + cls + '" title="' + esc(l.error || '') + '">' + esc(l.status || 'ERR') + '</span></td>' +
          '<td class="small">' + fa(l.duration_ms) + ' ms</td><td class="small mono">' + bytes(l.bytes_out) + '</td><td class="small mono dim">' + esc(l.client_ip || '') + '</td></tr>';
      }).join('') : '<tr><td colspan="8" class="empty">موردی یافت نشد</td></tr>';
    });
  }

  function vGuide() {
    var st = S.state, b = st.base_url, k = st.keys[0];
    var K = k ? k.key : 'YOUR_ACCESS_KEY';
    $('#view').innerHTML =
      '<div class="card"><div class="card-head"><h2>رله چطور کار می‌کند؟</h2></div>' +
      '<p class="muted">سرور شما در ایران به جای آدرس اصلی سرویس، درخواست را به این رله می‌فرستد. رله کلید دسترسی را بررسی می‌کند و درخواست را <b>بدون تغییر</b> (همراه استریم پاسخ) به مقصد منتقل می‌کند. فقط کافیست «آدرس پایه» را در کتابخانهٔ خود عوض کنید.</p>' +
      '<div class="grid grid-2" style="margin-top:16px"><div><h4 style="margin-bottom:8px">۱. کلید داخل آدرس</h4>' + codeBlock(b + '/' + K + '/<service>/<path>') + '</div>' +
      '<div><h4 style="margin-bottom:8px">۲. کلید در هدر</h4>' + codeBlock(b + '/<service>/<path>\nX-Relay-Key: ' + K) + '</div></div>' +
      '<div class="alert alert-info" style="margin-top:16px;margin-bottom:0"><b>دو حالت برای کلید API سرویس:</b><br>' +
      '• <b>عبوری</b>: کاربر کلید API خودش را مثل همیشه می‌فرستد و رله فقط آن را منتقل می‌کند.<br>' +
      '• <b>مدیریت‌شده</b>: کلید API (یا چند کلید برای چرخش) در رله ذخیره می‌شود؛ کاربر به جای آن فقط <b>کلید دسترسی رله</b> را به عنوان api_key می‌فرستد و کلید اصلی هیچ‌وقت به سرور ایران نمی‌رسد.</div>' +
      '<div class="alert alert-info" style="margin-top:12px;margin-bottom:0"><b>سازگار با رله‌های Cloudflare Worker:</b> برنامه‌هایی که آدرس را به شکل <code>' + esc(b) + '/&lt;host&gt;/&lt;path&gt;</code> می‌سازند و کلید را با هدر <code>X-Relay-Key</code> می‌فرستند (مثل حامی‌کار) بدون تغییر کار می‌کنند؛ کافیست سرویسی با همان host تعریف شده باشد.<br>' +
      '<b>متغیرها:</b> در ویرایش هر سرویس و هر کلید می‌توانید متغیر، هدر و پارامتر اضافه تعریف کنید تا همراه همهٔ درخواست‌ها به مقصد ارسال شود.</div></div>' +
      st.services.map(function (s) {
        return '<div class="card"><div class="card-head"><h2><span class="svc-icon" style="width:32px;height:32px;border-radius:9px">' + brand(s.preset) + '</span>' + esc(s.name) + ' <code class="small dim">/' + esc(s.slug) + '</code></h2>' +
          (s.managed ? '<span class="badge b-info">مدیریت‌شده</span>' : '<span class="badge b-mute">عبوری</span>') + '</div>' + snippetTabs(s, k) + '</div>';
      }).join('');
  }

  function vSettings() {
    var st = S.state.settings;
    $('#view').innerHTML = '<div class="grid grid-2"><div class="card"><div class="card-head"><h2>حساب مدیر</h2></div><form id="f-account" class="form-grid">' +
      field('نام کاربری', '<input class="input ltr" name="username" value="' + esc(st.admin_username) + '" required>', '', true) +
      field('رمز عبور فعلی', '<input class="input ltr" type="password" name="current_password" required autocomplete="current-password">') +
      field('رمز عبور جدید', '<input class="input ltr" type="password" name="new_password" autocomplete="new-password" placeholder="خالی = بدون تغییر">', 'حداقل ۸ کاراکتر') +
      '<div class="full"><button class="btn btn-primary">ذخیره</button></div></form></div>' +
      '<div class="card"><div class="card-head"><h2>تنظیمات عمومی</h2></div><form id="f-settings" class="form-grid">' +
      field('آدرس عمومی رله', '<input class="input ltr" name="public_url" value="' + esc(st.public_url || '') + '" placeholder="https://relay.example.com">', 'در کدهای نمونه استفاده می‌شود. خالی = تشخیص خودکار', true) +
      field('تعداد لاگ نگهداری‌شده', '<input class="input ltr" type="number" min="100" name="log_retention" value="' + esc(st.log_retention) + '">') +
      '<div class="field"><label>&nbsp;</label><label class="switch"><input type="checkbox" name="trust_proxy"' + (st.trust_proxy ? ' checked' : '') + '><span class="track"></span>پشت Cloudflare / پروکسی هستم</label><span class="hint">IP واقعی کاربر از هدرهای پروکسی خوانده شود</span></div>' +
      '<div class="full"><button class="btn btn-primary">ذخیره</button></div></form></div></div>' +
      '<div class="card"><div class="card-head"><h2>درباره</h2></div><p class="muted">Gozar Relay نسخهٔ ' + esc(S.state.version) + ' · نصب‌شده در ' + dateStr(st.installed_at) + '</p></div>';
    $('#f-account').onsubmit = function (e) {
      e.preventDefault();
      api('account', formData(e.target)).then(function () { toast('حساب بروزرسانی شد'); return load(); }).catch(function (er) { toast(er.message, true); });
    };
    $('#f-settings').onsubmit = function (e) {
      e.preventDefault();
      api('settings/save', formData(e.target)).then(function () { toast('ذخیره شد'); return load(); }).catch(function (er) { toast(er.message, true); });
    };
  }

  function field(label, input, hint, full) {
    return '<div class="field' + (full ? ' full' : '') + '"><label>' + label + '</label>' + input + (hint ? '<span class="hint">' + hint + '</span>' : '') + '</div>';
  }

  function formData(form) {
    var d = {};
    $$('input, select, textarea', form).forEach(function (el) {
      if (!el.name) return;
      if (el.type === 'checkbox') {
        if (el.dataset.multi) { (d[el.name] = d[el.name] || []); if (el.checked) d[el.name].push(el.value); }
        else d[el.name] = el.checked;
      } else d[el.name] = el.value;
    });
    return d;
  }

  // ----------------------------------------------------------------- modals
  function modal(title, body, foot, wide) {
    closeModal();
    var bg = document.createElement('div');
    bg.className = 'modal-bg';
    bg.id = 'modal';
    bg.innerHTML = '<div class="modal' + (wide ? ' wide' : '') + '"><div class="modal-head"><h3>' + title + '</h3><button class="btn btn-ghost btn-icon" data-act="close-modal">' + icon('x') + '</button></div>' +
      '<div class="modal-body">' + body + '</div>' + (foot ? '<div class="modal-foot">' + foot + '</div>' : '') + '</div>';
    bg.addEventListener('mousedown', function (e) { if (e.target === bg) closeModal(); });
    document.body.appendChild(bg);
    return bg;
  }
  function closeModal() { var m = $('#modal'); if (m) m.remove(); }

  function confirmBox(text, onYes) {
    var m = modal('تأیید', '<p>' + text + '</p>', '<button class="btn btn-danger" id="yes">بله، انجام بده</button><button class="btn" data-act="close-modal">انصراف</button>');
    $('#yes', m).onclick = function () { closeModal(); onYes(); };
  }

  function presetPicker() {
    var body = '<div class="svc-grid">' + S.state.presets.map(function (p) {
      return '<div class="card svc" style="cursor:pointer;padding:16px" data-act="pick-preset" data-preset="' + p.preset + '"><div class="svc-top"><div class="svc-icon">' + brand(p.preset) + '</div><div class="svc-title"><b>' + esc(p.name) + '</b><code>' + esc(p.upstream) + '</code></div></div>' +
        (p.hint ? '<div class="small muted">' + esc(p.hint) + '</div>' : '') + '</div>';
    }).join('') + '</div>';
    modal('انتخاب نوع سرویس', body, '', true);
  }

  function serviceForm(svc, preset) {
    var isNew = !svc;
    var p = preset || S.state.presets.filter(function (x) { return x.preset === (svc ? svc.preset : 'custom'); })[0];
    var v = svc || { slug: p.slug, name: p.name, upstream: p.upstream, auth_type: p.auth_type, auth_name: p.auth_name, timeout: p.timeout, enabled: true, cors: false, note: '', upstream_keys: [], preset: p.preset, variables: p.variables || '', headers: p.headers || '', params: '' };
    if (isNew && S.state.services.some(function (s) { return s.slug === v.slug; })) v.slug = v.slug ? v.slug + '-2' : '';
    var auth = [['none', 'هیچ'], ['bearer', 'Authorization: Bearer'], ['header', 'هدر سفارشی'], ['query', 'پارامتر Query']];
    var body = '<form id="f-svc" class="form-grid">' +
      '<input type="hidden" name="id" value="' + (svc ? svc.id : '') + '"><input type="hidden" name="preset" value="' + esc(v.preset) + '">' +
      field('نام نمایشی', '<input class="input" name="name" value="' + esc(v.name) + '" required>') +
      field('شناسه در آدرس (slug)', '<input class="input ltr" name="slug" value="' + esc(v.slug) + '" required pattern="[a-z][a-z0-9\\-]{1,31}">', 'مثلاً ' + esc(S.state.base_url) + '/<b>' + esc(v.slug || 'myapi') + '</b>/...') +
      field('آدرس مقصد (Upstream)', '<input class="input ltr" name="upstream" value="' + esc(v.upstream) + '" required>', 'تمام مسیرها بعد از slug به این آدرس اضافه می‌شوند', true) +
      '<div class="full alert alert-info" style="margin:0"><b>کلید API مدیریت‌شده (اختیاری)</b><br><span class="small">اگر کلید API سرویس را اینجا وارد کنید، رله خودش آن را به درخواست‌ها اضافه می‌کند و برنامه‌ها فقط با کلید دسترسی رله کار می‌کنند. چند کلید = هر خط یک کلید (چرخش تصادفی). خالی بگذارید تا حالت عبوری باشد.</span></div>' +
      field('روش ارسال کلید به مقصد', '<select name="auth_type">' + auth.map(function (a) { return '<option value="' + a[0] + '"' + (v.auth_type === a[0] ? ' selected' : '') + '>' + a[1] + '</option>'; }).join('') + '</select>') +
      field('نام هدر / پارامتر', '<input class="input ltr" name="auth_name" value="' + esc(v.auth_name) + '" placeholder="x-api-key">') +
      field('کلید(های) API سرویس', '<textarea class="input ltr mono" name="upstream_keys" placeholder="' + (svc && svc.managed ? 'کلیدهای فعلی: ' + esc(svc.upstream_keys.join('، ')) + ' — برای تغییر، کلیدهای جدید را وارد کنید' : 'sk-...') + '"></textarea>' +
        (svc && svc.managed ? '<label class="switch small"><input type="checkbox" name="clear_upstream_keys"><span class="track"></span>حذف کلیدهای ذخیره‌شده (بازگشت به حالت عبوری)</label>' : ''), '', true) +
      field('Timeout (ثانیه)', '<input class="input ltr" type="number" name="timeout" min="5" max="900" value="' + esc(v.timeout) + '">') +
      '<div class="field"><label>&nbsp;</label><div class="row"><label class="switch"><input type="checkbox" name="enabled"' + (v.enabled ? ' checked' : '') + '><span class="track"></span>فعال</label>' +
      '<label class="switch"><input type="checkbox" name="cors"' + (v.cors ? ' checked' : '') + '><span class="track"></span>CORS (مرورگر)</label></div></div>' +
      '<div class="full alert alert-info" style="margin:0"><b>متغیرها و داده‌های ارسالی (مثل Environment Variables در Cloudflare Worker)</b><br><span class="small">' +
        'متغیرها را با <code>NAME=value</code> تعریف کنید و در هدرها، پارامترها، آدرس مقصد و کلید API با <code>{{NAME}}</code> استفاده کنید. ' +
        'متغیرهای هر کلید دسترسی روی متغیرهای سرویس اولویت دارند. متغیرهای آماده: <code>{{KEY_NAME}}</code>، <code>{{KEY_ID}}</code>، <code>{{SERVICE}}</code>. ' +
        'مقدار متغیرهایی که نامشان KEY، SECRET، TOKEN یا PASS دارد در پنل مخفی نمایش داده می‌شود.</span></div>' +
      field('متغیرها', '<textarea class="input ltr mono" name="variables" rows="3" placeholder="SITE_NAME=Hamicar&#10;ACCOUNT_ID=abc123">' + esc(v.variables) + '</textarea>', 'هر خط: NAME=value', true) +
      field('هدرهای اضافه', '<textarea class="input ltr mono" name="headers" rows="3" placeholder="X-Title: {{SITE_NAME}}&#10;anthropic-version?: 2023-06-01">' + esc(v.headers) + '</textarea>', 'Header: value — با ? بعد از نام فقط وقتی برنامه نفرستاده باشد؛ مقدار خالی = حذف هدر', true) +
      field('پارامترهای Query اضافه', '<textarea class="input ltr mono" name="params" rows="2" placeholder="source={{KEY_NAME}}">' + esc(v.params) + '</textarea>', 'هر خط: name=value', true) +
      field('یادداشت', '<input class="input" name="note" value="' + esc(v.note) + '">', '', true) + '</form>';
    var m = modal((isNew ? 'افزودن ' : 'ویرایش ') + esc(v.name), body, '<button class="btn btn-primary" id="save">ذخیره</button><button class="btn" data-act="close-modal">انصراف</button>', true);
    $('#save', m).onclick = function () {
      var d = formData($('#f-svc'));
      d.id = d.id ? Number(d.id) : 0;
      api('services/save', d).then(function () { closeModal(); toast('سرویس ذخیره شد'); return load(); }).catch(function (e) { toast(e.message, true); });
    };
  }

  function keyForm(k) {
    var v = k || { name: '', services: ['*'], rate_limit: 0, note: '', enabled: true, expires_at: 0, variables: '' };
    var all = v.services.indexOf('*') >= 0;
    var exp = v.expires_at ? new Date(v.expires_at * 1000).toISOString().slice(0, 10) : '';
    var chips = '<label class="chip' + (all ? ' on' : '') + '"><input type="checkbox" data-multi="1" name="services" value="*"' + (all ? ' checked' : '') + '>همه</label>' +
      S.state.services.map(function (s) {
        var on = !all && v.services.indexOf(s.slug) >= 0;
        return '<label class="chip' + (on ? ' on' : '') + '"><input type="checkbox" data-multi="1" name="services" value="' + esc(s.slug) + '"' + (on ? ' checked' : '') + '>' + esc(s.name) + '</label>';
      }).join('');
    var body = '<form id="f-key" class="form-grid"><input type="hidden" name="id" value="' + (k ? k.id : '') + '">' +
      field('نام', '<input class="input" name="name" value="' + esc(v.name) + '" required placeholder="مثلاً: ربات پشتیبانی / حامی‌کار">') +
      field('محدودیت درخواست در دقیقه', '<input class="input ltr" type="number" min="0" name="rate_limit" value="' + esc(v.rate_limit) + '">', '۰ = نامحدود') +
      field('سرویس‌های مجاز', '<div class="chips">' + chips + '</div>', '', true) +
      field('تاریخ انقضا (اختیاری)', '<input class="input ltr" type="date" name="expires" value="' + exp + '">') +
      field(k ? 'کلید' : 'کلید دلخواه (اختیاری)', k ? '<div class="row"><span class="key-pill">' + esc(k.key) + '</span><button type="button" class="btn btn-sm" data-act="rotate-key" data-id="' + k.id + '">' + icon('refresh') + 'تولید کلید جدید</button></div>' : '<input class="input ltr" name="key" placeholder="خالی = تولید خودکار">') +
      field('متغیرهای اختصاصی این کلید', '<textarea class="input ltr mono" name="variables" rows="3" placeholder="SITE_NAME=Hamicar&#10;OPENROUTER_KEY=sk-or-...">' + esc(v.variables) + '</textarea>',
        'روی متغیرهای هم‌نام سرویس اولویت دارند. مثلاً اگر کلید API سرویس را <code>{{OPENROUTER_KEY}}</code> بگذارید، هر کلید دسترسی با کلید API خودش کار می‌کند.', true) +
      field('یادداشت', '<input class="input" name="note" value="' + esc(v.note) + '">', '', true) +
      '<div class="field full"><label class="switch"><input type="checkbox" name="enabled"' + (v.enabled ? ' checked' : '') + '><span class="track"></span>فعال</label></div></form>';
    var m = modal(k ? 'ویرایش کلید' : 'کلید دسترسی جدید', body, '<button class="btn btn-primary" id="save">ذخیره</button><button class="btn" data-act="close-modal">انصراف</button>');
    $$('.chip input', m).forEach(function (cb) {
      cb.onchange = function () {
        if (cb.value === '*' && cb.checked) $$('.chip input', m).forEach(function (o) { if (o !== cb) o.checked = false; });
        if (cb.value !== '*' && cb.checked) $('.chip input[value="*"]', m).checked = false;
        $$('.chip', m).forEach(function (c) { c.classList.toggle('on', $('input', c).checked); });
      };
    });
    $('#save', m).onclick = function () {
      var d = formData($('#f-key'));
      d.id = d.id ? Number(d.id) : 0;
      d.expires_at = d.expires ? Math.floor(new Date(d.expires + 'T23:59:59').getTime() / 1000) : 0;
      delete d.expires;
      api('keys/save', d).then(function (r) {
        closeModal(); toast('کلید ذخیره شد');
        return load().then(function () { if (!k) snippetForKey(r.key); });
      }).catch(function (e) { toast(e.message, true); });
    };
  }

  function snippetForKey(k) {
    var allowed = S.state.services.filter(function (s) { return k.services.indexOf('*') >= 0 || k.services.indexOf(s.slug) >= 0; });
    var body = '<div class="alert alert-info">کلید <span class="key-pill">' + esc(k.key) + '<button data-copy="' + esc(k.key) + '">کپی</button></span> برای «' + esc(k.name) + '»</div>' +
      allowed.map(function (s) {
        return '<h4 class="row" style="margin:18px 0 8px"><span class="svc-icon" style="width:28px;height:28px;border-radius:8px">' + brand(s.preset) + '</span>' + esc(s.name) + '</h4><div class="snip">' + snippetTabs(s, k) + '</div>';
      }).join('');
    modal('کد اتصال', body, '', true);
  }

  function snippetForService(s) {
    var k = S.state.keys.filter(function (x) { return x.enabled && (x.services.indexOf('*') >= 0 || x.services.indexOf(s.slug) >= 0); })[0];
    modal('کد اتصال — ' + esc(s.name), (k ? '<p class="small muted" style="margin-bottom:12px">نمونه با کلید «' + esc(k.name) + '»</p>' : '<div class="alert alert-warn">هیچ کلید فعالی برای این سرویس وجود ندارد.</div>') + snippetTabs(s, k), '', true);
  }

  // ---------------------------------------------------------------- actions
  function svcById(id) { return S.state.services.filter(function (s) { return s.id === Number(id); })[0]; }
  function keyById(id) { return S.state.keys.filter(function (k) { return k.id === Number(id); })[0]; }

  var ACT = {
    'close-modal': closeModal,
    'toggle-relay': function () {
      var on = S.state.settings.enabled;
      var go = function () { api('relay/toggle', {}).then(function () { toast(on ? 'رله خاموش شد' : 'رله روشن شد'); load(); }); };
      on ? confirmBox('با خاموش کردن رله، تمام برنامه‌ها قطع می‌شوند. ادامه می‌دهید؟', go) : go();
    },
    'test-all': testAll,
    'add-service': presetPicker,
    'pick-preset': function (el) { serviceForm(null, S.state.presets.filter(function (p) { return p.preset === el.dataset.preset; })[0]); },
    'edit-service': function (el) { serviceForm(svcById(el.dataset.id)); },
    'snip-service': function (el) { snippetForService(svcById(el.dataset.id)); },
    'test-service': function (el) {
      el.disabled = true;
      api('services/test', { id: Number(el.dataset.id) }).then(function (r) {
        toast((r.ok ? 'در دسترس — ' : 'خطا — ') + r.detail + ' (' + r.ms + 'ms)', !r.ok);
      }).finally(function () { el.disabled = false; });
    },
    'del-service': function (el) {
      var s = svcById(el.dataset.id);
      confirmBox('سرویس «' + esc(s.name) + '» حذف شود؟ برنامه‌هایی که از آدرس /' + esc(s.slug) + ' استفاده می‌کنند قطع خواهند شد.', function () {
        api('services/delete', { id: s.id }).then(function () { toast('حذف شد'); load(); });
      });
    },
    'add-key': function () { keyForm(null); },
    'edit-key': function (el) { keyForm(keyById(el.dataset.id)); },
    'snip-key': function (el) { snippetForKey(keyById(el.dataset.id)); },
    'toggle-key': function (el) {
      var k = keyById(el.dataset.id);
      api('keys/save', { id: k.id, name: k.name, services: k.services, rate_limit: k.rate_limit, note: k.note, variables: k.variables, enabled: !k.enabled })
        .then(function () { toast('وضعیت کلید تغییر کرد'); load(); }).catch(function (e) { toast(e.message, true); });
    },
    'rotate-key': function (el) {
      confirmBox('کلید فعلی بلافاصله از کار می‌افتد و باید کلید جدید را در برنامه‌ها جایگزین کنید. ادامه؟', function () {
        api('keys/rotate', { id: Number(el.dataset.id) }).then(function (r) { toast('کلید جدید ساخته شد'); load().then(function () { snippetForKey(r.key); }); });
      });
    },
    'del-key': function (el) {
      var k = keyById(el.dataset.id);
      confirmBox('کلید «' + esc(k.name) + '» برای همیشه حذف شود؟', function () {
        api('keys/delete', { id: k.id }).then(function () { toast('حذف شد'); load(); });
      });
    },
    'reload-logs': loadLogs,
    'clear-logs': function () { confirmBox('همهٔ گزارش‌ها پاک شوند؟', function () { api('logs/clear', {}).then(function () { toast('پاک شد'); loadLogs(); load(); }); }); }
  };

  document.addEventListener('click', function (e) {
    var t = e.target.closest('[data-copy]');
    if (t) { e.preventDefault(); copy(t.dataset.copy); return; }
    t = e.target.closest('[data-nav]');
    if (t) { S.view = t.dataset.nav; location.hash = S.view; render(); window.scrollTo(0, 0); return; }
    t = e.target.closest('[data-tab]');
    if (t) {
      var wrap = t.parentNode.parentNode;
      $$('.tab', t.parentNode).forEach(function (x) { x.classList.toggle('active', x === t); });
      $$('[data-pane]', wrap).forEach(function (p) { p.hidden = p.dataset.pane !== t.dataset.tab; });
      return;
    }
    t = e.target.closest('[data-act]');
    if (t && ACT[t.dataset.act]) { e.preventDefault(); ACT[t.dataset.act](t); }
  });

  document.addEventListener('change', function (e) {
    if (e.target.id === 'lf-service') { S.logFilter.service = e.target.value; loadLogs(); }
    if (e.target.id === 'lf-key') { S.logFilter.key_id = e.target.value; loadLogs(); }
    if (e.target.id === 'lf-err') { S.logFilter.errors = e.target.checked; loadLogs(); }
  });
  document.addEventListener('keydown', function (e) { if (e.key === 'Escape') closeModal(); });
  window.addEventListener('hashchange', function () {
    var v = location.hash.slice(1);
    if (v && v !== S.view) { S.view = v; render(); }
  });

  load().catch(function (e) {
    $('#app').innerHTML = '<div class="loading-screen">خطا در بارگذاری: ' + esc(e.message) + '</div>';
  });
})();
