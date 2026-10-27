"""Редактор в настоящем браузере (Chrome headless): загрузка фото с белым фоном → удаление фона → порты мышью → приближение → проверка → сборка zip.
Страница читается через --dump-dom (порт отладки на этом ПК запрещён). Запуск: python tests/test_editor_browser.py [--shot путь.png]"""
import json, os, re, shutil, subprocess, sys, tempfile

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
chrome = next((p for p in (r'C:\Program Files\Google\Chrome\Application\chrome.exe', r'C:\Program Files (x86)\Google\Chrome\Application\chrome.exe',
                           r'C:\Program Files (x86)\Microsoft\Edge\Application\msedge.exe') if os.path.isfile(p)), None)
if not chrome:
    print('нет Chrome — проверка в браузере пропущена\n\nВСЁ OK'); sys.exit(0)
shot = sys.argv[sys.argv.index('--shot') + 1] if '--shot' in sys.argv else None
html = open(os.path.join(ROOT, 'docs', 'index.html'), encoding='utf-8').read()
TEST = r'''
<pre id="res">RUNNING</pre>
<script>
(async () => {
  const out = [], t = (n, ok, x) => out.push([n, !!ok, x === undefined ? '' : String(x)]), sleep = ms => new Promise(r => setTimeout(r, ms));
  const errs = []; window.addEventListener('error', e => errs.push(e.message));
  try {
    const E = window.__ed, S = E.S;
    const c = document.createElement('canvas'); c.width = 1000; c.height = 220; const x = c.getContext('2d');
    x.fillStyle = '#fff'; x.fillRect(0, 0, 1000, 220); x.fillStyle = '#3c4046'; x.fillRect(60, 40, 880, 140);
    x.fillStyle = '#111'; for (let i = 0; i < 8; i++) x.fillRect(120 + i * 70, 90, 40, 40);
    S.orig = c; S.bgOn = true; S.crop = true; E.process(); for (let i = 0; i < 60 && !S.photoFile; i++) await sleep(250);
    t('фото обработано: файл есть', !!S.photoFile && !!S.photoBlob, S.photoFile);
    t('белый фон убран: края прозрачны', S.px && S.px.borderClear >= .97, JSON.stringify(S.px));
    t('обрезано по устройству с полем', S.work.width < 1000 && S.work.width > 880, S.work.width + 'x' + S.work.height);
    t('размер в пределах', S.px.bytes <= 614400 && S.px.longSide >= 600 ? true : S.px.longSide < 600 ? 'малое' : false, JSON.stringify(S.px));
    S.tab = 1; E.render(); await sleep(100);
    const ov = document.getElementById('ov'), r = ov.getBoundingClientRect();
    const fire = (type, fx, fy, target) => (target || ov).dispatchEvent(new PointerEvent(type, { bubbles: true, cancelable: true, pointerId: 1, clientX: r.left + fx * r.width, clientY: r.top + fy * r.height }));
    const lp = () => document.querySelector('.lp'), shown = () => lp() && lp().style.display === 'block';
    let during = null;
    const place = (x0, y0, x1, y1) => { fire('pointerdown', x0, y0); fire('pointermove', (x0 + x1) / 2, (y0 + y1) / 2); fire('pointermove', x1, y1); during = shown(); fire('pointerup', x1, y1); };
    t('область рисования имеет размер', r.width > 100 && r.height > 20, r.width + 'x' + r.height);
    place(.10, .40, .12, .50); const loupeOn = during; place(.30, .40, .30, .50);
    t('поставлены 2 порта с номерами 1 и 2, метка там, где отпустили', S.spots.length === 2 && S.spots[0].n === 1 && S.spots[1].n === 2 && Math.abs(S.spots[0].x - .12) < .01 && Math.abs(S.spots[0].y - .5) < .01, JSON.stringify(S.spots));
    t('лупа видна, пока палец на фото, и пропадает после', loupeOn === true && !shown(), String(loupeOn));
    t('касание рядом с готовой меткой берёт её, а не ставит новую', (() => { const n = S.spots.length; fire('pointerdown', .121, .5); fire('pointerup', .121, .5); return S.spots.length === n && S.sel === 1; })());
    t('касание пустого места ставит метку', (() => { const n = S.spots.length; fire('pointerdown', .8, .5); fire('pointerup', .8, .5); const ok = S.spots.length === n + 1; S.spots.pop(); return ok; })());
    S.sel = 1; E.render(); document.getElementById('rc').value = 5; document.getElementById('rep').click(); await sleep(50);
    t('«Размножить» добавило 5 копий (всего 7)', S.spots.length === 7, S.spots.length);
    document.getElementById('rn2').click(); await sleep(50);
    t('перетаскивание порта двигает его', (() => { const s0 = S.spots[0], cx = s0.x, cy = s0.y; const el = ov.querySelector('.pt'); fire('pointerdown', cx, cy, el); fire('pointermove', cx + .1, cy); fire('pointerup', cx + .1, cy); return Math.abs(S.spots.find(q => q.n === s0.n).x - (cx + .1)) < .02; })());
    document.querySelector('[data-t="2"]').click(); await sleep(50);
    document.getElementById('zauto').click(); await sleep(50);
    t('зона приближения «по портам» задана и внутри кадра', S.zoom && S.zoom.x >= 0 && S.zoom.x + S.zoom.w <= 1.0001, JSON.stringify(S.zoom));
    document.getElementById('pv').click(); await sleep(100);
    t('предпросмотр приближения применяет transform', document.getElementById('zoomer').style.transform.startsWith('scale('), document.getElementById('zoomer').style.transform);
    document.getElementById('pv').click(); await sleep(100);
    t('«Отдалить» возвращает transform в none', document.getElementById('zoomer').style.transform === 'none');
    document.querySelector('[data-t="3"]').click(); await sleep(50);
    const set = (id, v) => { const e = document.getElementById(id); e.value = v; e.dispatchEvent(new Event('input', { bubbles: true })); };
    set('vendor', 'TP-Link'); set('model', 'DEMO-8'); 
    document.querySelector('[data-t="4"]').click(); await sleep(100);
    t('без галочки прав кнопка «Скачать» заблокирована', document.getElementById('dl').disabled === true);
    const cb = document.getElementById('rights'); cb.checked = true; cb.dispatchEvent(new Event('input', { bubbles: true })); E.render(); await sleep(100);
    t('с галочкой прав кнопка «Скачать» доступна', document.getElementById('dl').disabled === false, JSON.stringify(E.checkState(S, S.px).filter(q => q.level === 'bad')));
    t('ссылка на заявку ведёт на GitHub', /^https:\/\/github\.com\/[^/]+\/racklive-models\/issues\/new/.test(document.getElementById('gh').href), document.getElementById('gh').href);
    t('модель собирается', E.buildModel(S).model.spots.length === 7 && E.buildModel(S).id === 'tp-link-demo-8');
  } catch (e) { t('исключение', false, e.stack || e); }
  t('нет ошибок JavaScript на странице', errs.length === 0, errs.join(' | '));
  document.getElementById('res').textContent = 'RESULT' + JSON.stringify(out) + 'END';
})();
</script>'''
tmp = tempfile.mkdtemp()
try:
    p = os.path.join(tmp, 'ed.html'); open(p, 'w', encoding='utf-8').write(html.replace('</body>', TEST + '</body>'))
    ud = os.path.join(tmp, 'prof')
    base = [chrome, '--headless=new', '--disable-gpu', '--no-first-run', f'--user-data-dir={ud}', '--window-size=900,1000', '--allow-file-access-from-files']
    r = subprocess.run(base + ['--virtual-time-budget=15000', '--dump-dom', 'file:///' + p.replace('\\', '/')], capture_output=True, text=True, encoding='utf-8', timeout=120)
    m = re.search(r'RESULT(\[.*?\])END', r.stdout, re.S)
    if not m:
        print('нет результата. вывод:', r.stdout[-600:], r.stderr[-400:]); sys.exit(1)
    bad = []
    for name, ok, extra in json.loads(m.group(1).replace('&quot;', '"').replace('&amp;', '&').replace('&lt;', '<').replace('&gt;', '>')):
        print(('  ok   ' if ok is True or ok == 'малое' else '  FAIL ') + name + ('' if ok or not extra else ' — ' + extra))
        if not ok: bad.append(name)
    if shot:
        subprocess.run(base + ['--virtual-time-budget=15000', f'--screenshot={shot}', 'file:///' + p.replace('\\', '/')], capture_output=True, timeout=120)
    print('\n' + ('ВСЁ OK' if not bad else 'ОШИБКИ: ' + ', '.join(bad)))
    sys.exit(1 if bad else 0)
finally:
    shutil.rmtree(tmp, ignore_errors=True)
