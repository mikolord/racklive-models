"""Логика редактора (docs/index.html, блок CORE) — в Node, и сквозная проверка: zip, собранный редактором, проходит проверку каталога.
Запуск: python tests/test_editor_core.py"""
import base64, io, json, os, shutil, subprocess, sys, tempfile, zipfile

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, 'tools'))
import validate
from PIL import Image, ImageDraw

node = shutil.which('node')
if not node:
    print('нет Node — проверка редактора пропущена\n\nВСЁ OK'); sys.exit(0)
html = open(os.path.join(ROOT, 'docs', 'index.html'), encoding='utf-8').read()
core = html[html.index('// CORE-START'):html.index('// CORE-END')]

im = Image.new('RGBA', (900, 160), (0, 0, 0, 0)); ImageDraw.Draw(im).rectangle([20, 20, 880, 140], fill=(60, 64, 70, 255))
buf = io.BytesIO(); im.save(buf, 'WEBP'); photo_b64 = base64.b64encode(buf.getvalue()).decode()

js = core + r'''
const out = [], t = (n, ok, x) => out.push([n, !!ok, x === undefined ? '' : String(x)]);
const near = (a, b, e = 1e-6) => Math.abs(a - b) <= e;
t('slugify: латиница и пробелы', slugify('TP-Link T2600G (v4)') === 'tp-link-t2600g-v4', slugify('TP-Link T2600G (v4)'));
t('slugify: кириллица', slugify('Микротик Хап') === 'mikrotik-hap', slugify('Микротик Хап'));
t('modelId короткий — дополняется', modelId('A', 'b').length >= 3, modelId('A', 'b'));
t('nextN: первое свободное', nextN([{ n: 1 }, { n: 2 }, { n: 4 }]) === 3);
const sp = (n, x, y) => ({ n, x, y, w: .04, h: .1, kind: 'rj45', label: '' });
t('fitSpot держит порт в кадре', (s => s.x - s.w / 2 >= 0 && s.y + s.h / 2 <= 1)(fitSpot({ n: 1, x: -.5, y: 1.5, w: .04, h: .1 })));
t('fitSpot ограничивает размер .6', fitSpot({ n: 1, x: .5, y: .5, w: .9, h: .9 }).w === .6);
const two = [sp(9, .1, .3), sp(8, .2, .3), sp(7, .1, .7), sp(6, .2, .7)];
t('нумерация по строкам', JSON.stringify(renumber(two, 'rows').map(s => s.n)) === JSON.stringify([1, 2, 3, 4]), JSON.stringify(renumber(two, 'rows').map(s => s.n)));
t('нумерация по колонкам: сверху нечётные', JSON.stringify(renumber(two, 'cols').map(s => s.n)) === JSON.stringify([1, 3, 2, 4]), JSON.stringify(renumber(two, 'cols').map(s => s.n)));
const rep = repeatSpots([sp(1, .1, .5)], sp(1, .1, .5), 5, .06);
t('размножение: 5 копий с нумерацией 2…6', rep.length === 5 && rep[0].n === 2 && rep[4].n === 6 && near(rep[4].x, .4), JSON.stringify(rep.map(s => [s.n, s.x])));
t('размножение останавливается у края фото', repeatSpots([sp(1, .1, .5)], sp(1, .1, .5), 48, .06).length < 48);
const ai = parseAI('Вот ответ:\n```json\n{"spots":[{"n":1,"x":12.5,"y":40,"w":3,"h":9,"kind":"sfp","label":"WAN"},{"n":1,"x":50,"y":50,"w":3,"h":9},{"n":2,"x":"bad"}],"zoom":{"x":8,"y":30,"w":60,"h":40}}\n```');
t('ответ ИИ: проценты → доли, дубли и мусор отброшены', ai.spots.length === 1 && near(ai.spots[0].x, .125) && ai.spots[0].kind === 'sfp' && ai.spots[0].label === 'WAN', JSON.stringify(ai.spots));
t('ответ ИИ: зона приближения', ai.zoom && near(ai.zoom.x, .08) && near(ai.zoom.w, .6), JSON.stringify(ai.zoom));
let threw = false; try { parseAI('никакого json'); } catch (e) { threw = true; } t('ответ ИИ без JSON — понятная ошибка', threw);
t('зона приближения: центр на (0.5, 0.5) не двигается', zoomTransform({ x: .25, y: .25, w: .5, h: .5 }) === 'scale(2) translate(0%, 0%)', zoomTransform({ x: .25, y: .25, w: .5, h: .5 }));
t('зона приближения: масштаб не больше 6', zoomTransform({ x: .4, y: .4, w: .02, h: .02 }).startsWith('scale(6)'));
const st = { vendor: 'TP-Link', model: 'DEMO-24', title: '', notes: '', kind: 'switch', photoFile: 'photo.webp', license: 'own', author: '', source: '', rights: true, model3d: null,
  spots: [{ n: 2, x: .3, y: .5, w: .04, h: .3, kind: 'rj45', label: '' }, { n: 1, x: .2, y: .5, w: .04, h: .3, kind: 'sfp', label: 'WAN' }], zoom: { x: .1, y: .2, w: .5, h: .6 } };
const b = buildModel(st);
t('модель: id, папка, порядок портов', b.id === 'tp-link-demo-24' && b.dir === 'models/tp-link/tp-link-demo-24' && b.model.spots[0].n === 1 && b.model.spots[0].kind === 'sfp' && b.model.spots[1].kind === undefined, JSON.stringify(b.model.spots));
t('модель: pzoom и фото', b.model.pzoom.w === .5 && b.model.photo.file === 'photo.webp');
const px = { w: 900, h: 160, longSide: 900, bytes: 20000, borderClear: 1 };
t('проверка: хорошее состояние без ошибок', !checkState(st, px).some(r => r.level === 'bad'), JSON.stringify(checkState(st, px).filter(r => r.level === 'bad')));
t('проверка: без прав на фото — ошибка', checkState({ ...st, rights: false }, px).some(r => r.level === 'bad' && /прав/.test(r.text)));
t('проверка: непрозрачный фон — ошибка', checkState(st, { ...px, borderClear: .2 }).some(r => r.level === 'bad' && /Прозрачный/.test(r.text)));
t('проверка: CC BY без автора — ошибка', checkState({ ...st, license: 'CC-BY-4.0', source: 'https://e.org/p' }, px).some(r => r.level === 'bad' && /автор/.test(r.text)));
t('проверка: источник не https — ошибка', checkState({ ...st, license: 'CC0-1.0', source: 'http://x' }, px).some(r => r.level === 'bad' && /https/.test(r.text)));
t('crc32("123456789") = cbf43926', crc32(new TextEncoder().encode('123456789')) === 0xcbf43926);
const photo = Uint8Array.from(Buffer.from(process.argv[2], 'base64'));
const zip = makeZip([{ name: b.dir + '/model.json', data: new TextEncoder().encode(JSON.stringify(b.model, null, 1)) }, { name: b.dir + '/photo.webp', data: photo }]);
require('fs').writeFileSync(process.argv[3], Buffer.from(zip));
console.log(JSON.stringify(out));
'''
tmp = tempfile.mkdtemp()
BAD = []
try:
    jp = os.path.join(tmp, 'core.js'); open(jp, 'w', encoding='utf-8').write(js)
    zp = os.path.join(tmp, 'm.zip')
    r = subprocess.run([node, jp, photo_b64, zp], capture_output=True, text=True, encoding='utf-8', timeout=60)
    if r.returncode:
        print('Node упал:', r.stderr[:800]); sys.exit(1)
    for name, ok, extra in json.loads(r.stdout.strip().splitlines()[-1]):
        print(('  ok   ' if ok else '  FAIL ') + name + ('' if ok or not extra else ' — ' + extra))
        if not ok: BAD.append(name)
    # сквозная: zip редактора → распаковка в каталог → проверка
    with zipfile.ZipFile(zp) as z:
        bad = z.testzip()
        print(('  ok   ' if bad is None else '  FAIL ') + 'zip читается стандартным zipfile (контрольные суммы сходятся)')
        if bad: BAD.append('zip')
        names = z.namelist()
        z.extractall(tmp)
    d = os.path.join(tmp, 'models', 'tp-link', 'tp-link-demo-24')
    res = validate.check_dir(d)
    print(('  ok   ' if res['ok'] else '  FAIL ') + 'модель из zip редактора проходит проверку каталога' + ('' if res['ok'] else ' — ' + ' | '.join(res['errors'])))
    if not res['ok']: BAD.append('e2e')
finally:
    shutil.rmtree(tmp, ignore_errors=True)
print('\n' + ('ВСЁ OK' if not BAD else 'ОШИБКИ: ' + ', '.join(BAD)))
sys.exit(1 if BAD else 0)
