"""Проверка проверяющего: хорошая модель проходит, каждая из типичных ошибок отклоняется. Запуск: python tests/test_validate.py"""
import copy, io, json, os, shutil, sys, tempfile

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, 'tools'))
import validate, build_index, rl_models3d as m3d
from PIL import Image, ImageDraw

BAD, N = [], 0


def check(name, ok, extra=''):
    global N
    N += 1
    print(('  ok   ' if ok else '  FAIL ') + name + ('' if ok or not extra else ' — ' + str(extra)))
    if not ok:
        BAD.append(name)


def photo(path, transparent=True, size=(900, 160), fmt='WEBP', margin=20, exif=False):
    im = Image.new('RGBA', size, (0, 0, 0, 0) if transparent else (255, 255, 255, 255))
    ImageDraw.Draw(im).rectangle([margin, margin, size[0] - margin, size[1] - margin], fill=(60, 64, 70, 255))
    kw = {}
    if exif:
        e = Image.Exif(); e[0x010F] = 'Camera'; kw['exif'] = e
    im.save(path, fmt, **kw)


GOOD = {'format': 'racklive-card', 'version': 1, 'id': 'tp-link-demo', 'vendor': 'TP-Link', 'model': 'DEMO-24', 'kind': 'switch', 'title': 'TP-Link DEMO-24',
        'photo': {'file': 'photo.webp', 'license': 'own', 'author': 'Автор', 'source': ''},
        'spots': [{'n': 1, 'x': .2, 'y': .5, 'w': .04, 'h': .3, 'kind': 'rj45'}, {'n': 2, 'x': .3, 'y': .5, 'w': .04, 'h': .3, 'label': 'WAN'}],
        'pzoom': {'x': .1, 'y': .2, 'w': .5, 'h': .6}}


def make(root, mid='tp-link-demo', vendor='tp-link', meta=None, ph=None, extra=None, drop=()):
    d = os.path.join(root, 'models', vendor, mid)
    os.makedirs(d, exist_ok=True)
    m = copy.deepcopy(GOOD); m['id'] = mid
    for k, v in (meta or {}).items():
        if v is None:
            m.pop(k, None)
        else:
            m[k] = v
    json.dump(m, open(os.path.join(d, 'model.json'), 'w', encoding='utf-8'), ensure_ascii=False)
    if ph != 'none':
        (ph or (lambda p: photo(p)))(os.path.join(d, 'photo.webp'))
    for f, c in (extra or {}).items():
        open(os.path.join(d, f), 'w', encoding='utf-8').write(c)
    return d


def errs(d):
    r = validate.check_dir(d)
    return r['ok'], ' | '.join(r['errors'])


tmp = tempfile.mkdtemp()
try:
    ok, e = errs(make(tmp))
    check('хорошая модель проходит', ok, e)
    ok, e = errs(make(tmp, 'png-ok', meta={'photo': {'file': 'photo.png', 'license': 'own'}}, ph=lambda p: None, extra={}))
    check('нет файла фото — ошибка', not ok and 'нет в папке' in e, e)

    d = make(tmp, 'white-bg', ph=lambda p: photo(p, transparent=False))
    ok, e = errs(d); check('белый фон отклоняется', not ok and 'прозрачн' in e, e)
    d = make(tmp, 'no-margin', ph=lambda p: photo(p, margin=0))
    ok, e = errs(d); check('устройство впритык к краю (нет прозрачного поля) отклоняется', not ok and 'прозрачн' in e, e)           # целиком непрозрачный кадр WebP сохраняется без альфы — тоже отказ
    d = make(tmp, 'tiny', ph=lambda p: photo(p, size=(300, 60), margin=5))
    ok, e = errs(d); check('слишком маленькое фото отклоняется', not ok and 'не меньше 600' in e, e)
    d = make(tmp, 'huge', ph=lambda p: photo(p, size=(2000, 300), margin=20))
    ok, e = errs(d); check('слишком большое фото отклоняется', not ok and 'не больше 1600' in e, e)
    d = make(tmp, 'exifed', ph=lambda p: photo(p, exif=True))
    ok, e = errs(d); check('метаданные EXIF отклоняются', not ok and 'метаданные' in e, e)
    d = make(tmp, 'fake', ph=lambda p: open(p, 'wb').write(b'GIF89a' + os.urandom(400)))
    ok, e = errs(d); check('чужой файл под видом WebP отклоняется', not ok and 'не является настоящим' in e, e)

    def big(p):
        im = Image.effect_noise((1600, 400), 90).convert('RGBA'); im.putalpha(Image.new('L', (1600, 400), 255))
        ImageDraw.Draw(im).rectangle([0, 0, 1599, 30], fill=(0, 0, 0, 0)); ImageDraw.Draw(im).rectangle([0, 370, 1599, 399], fill=(0, 0, 0, 0))
        ImageDraw.Draw(im).rectangle([0, 0, 30, 399], fill=(0, 0, 0, 0)); ImageDraw.Draw(im).rectangle([1569, 0, 1599, 399], fill=(0, 0, 0, 0))
        im.save(p, 'PNG')
    d = make(tmp, 'heavy', meta={'photo': {'file': 'photo.png', 'license': 'own'}}, ph=lambda p: None); big(os.path.join(d, 'photo.png'))
    ok, e = errs(d); check('файл тяжелее 600 КБ отклоняется', not ok and 'КБ' in e, e)

    ok, e = errs(make(tmp, 'extra-file', extra={'run.sh': 'echo hi'}))
    check('лишний файл (скрипт) отклоняется', not ok and 'лишний файл' in e, e)
    ok, e = errs(make(tmp, 'wrong-id', meta={'id': 'other-id'}))
    check('id не совпадает с папкой — отклоняется', not ok and 'совпадать' in e, e)
    d = make(tmp, 'bad-slug-x'); os.rename(d, os.path.join(os.path.dirname(d), 'Bad_Slug')); ok, e = errs(os.path.join(os.path.dirname(d), 'Bad_Slug'))
    check('имя папки с заглавными и подчёркиванием отклоняется', not ok and 'только из строчных' in e, e)
    ok, e = errs(make(tmp, 'dup-port', meta={'spots': [{'n': 1, 'x': .2, 'y': .5, 'w': .04, 'h': .3}, {'n': 1, 'x': .3, 'y': .5, 'w': .04, 'h': .3}]}))
    check('порт с одним номером дважды отклоняется', not ok and 'дважды' in e, e)
    ok, e = errs(make(tmp, 'port-big', meta={'spots': [{'n': 1, 'x': .2, 'y': .5, 'w': .9, 'h': .3}]}))
    check('порт во пол-фото отклоняется', not ok and 'w и h' in e, e)
    ok, e = errs(make(tmp, 'port-out', meta={'spots': [{'n': 1, 'x': 1.4, 'y': .5, 'w': .04, 'h': .3}]}))
    check('порт за пределами фото отклоняется', not ok and 'x и y' in e, e)
    ok, e = errs(make(tmp, 'unk-field', meta={'script': 'x'}))
    check('неизвестное поле отклоняется', not ok and 'неизвестное поле' in e, e)
    ok, e = errs(make(tmp, 'zoom-out', meta={'pzoom': {'x': .7, 'y': .2, 'w': .6, 'h': .6}}))
    check('приближение за краем фото отклоняется', not ok and 'pzoom' in e, e)
    ok, e = errs(make(tmp, 'no-lic', meta={'photo': {'file': 'photo.webp'}}))
    check('фото без лицензии отклоняется', not ok and 'license' in e, e)
    ok, e = errs(make(tmp, 'cc-noauth', meta={'photo': {'file': 'photo.webp', 'license': 'CC-BY-4.0', 'source': 'https://example.org/p'}}))
    check('CC BY без автора отклоняется', not ok and 'автора' in e, e)
    ok, e = errs(make(tmp, 'foreign', meta={'photo': {'file': 'photo.webp', 'license': 'CC0-1.0'}}))
    check('чужое фото без источника отклоняется', not ok and 'source' in e, e)
    ok, e = errs(make(tmp, 'cc-ok', meta={'photo': {'file': 'photo.webp', 'license': 'CC-BY-4.0', 'author': 'Иван', 'source': 'https://example.org/p'}}))
    check('CC BY с автором и источником проходит', ok, e)
    ok, e = errs(make(tmp, 'js-src', meta={'photo': {'file': 'photo.webp', 'license': 'CC0-1.0', 'source': 'javascript:alert(1)'}}))
    check('источник не https отклоняется', not ok and 'https' in e, e)
    ok, e = errs(make(tmp, 'ctrl', meta={'title': 'a\x00b'}))
    check('управляющие символы в тексте отклоняются', not ok and 'служебные' in e, e)
    ok, e = errs(make(tmp, 'no-media', meta={'photo': None, 'spots': None, 'pzoom': None}, ph='none'))
    check('ни фото, ни 3D — отклоняется', not ok and 'хотя бы одно' in e, e)
    ok, e = errs(make(tmp, 'spots-nophoto', meta={'photo': None, 'pzoom': None}, ph='none'))
    check('точки без фото отклоняются', not ok and 'фото в заявке нет' in e, e)

    # 3D: только 3D-модель, и испорченная 3D-модель
    free = json.dumps(m3d.free_example(), ensure_ascii=False)
    ok, e = errs(make(tmp, 'only-3d', meta={'photo': None, 'spots': None, 'pzoom': None, 'model3d': 'model3d.json'}, ph='none', extra={'model3d.json': free}))
    check('только 3D-модель проходит', ok, e)
    bad3 = json.loads(free); bad3['size']['w'] = 99999
    ok, e = errs(make(tmp, 'bad-3d', meta={'photo': None, 'spots': None, 'pzoom': None, 'model3d': 'model3d.json'}, ph='none', extra={'model3d.json': json.dumps(bad3)}))
    check('испорченная 3D-модель отклоняется (правила Rack Live)', not ok and 'model3d.json' in e, e)
    ok, e = errs(make(tmp, 'orphan-3d', ph='none', extra={'model3d.json': free}, meta={'photo': None, 'spots': None, 'pzoom': None}))
    check('3D-файл, не указанный в model.json, отклоняется', not ok, e)

    # warning: порт на прозрачном месте
    r = validate.check_dir(make(tmp, 'warn-port', meta={'spots': [{'n': 1, 'x': .01, 'y': .01, 'w': .02, 'h': .02}]}))
    check('порт на прозрачном месте — предупреждение, не ошибка', r['ok'] and any('прозрачном' in w for w in r['warnings']), r)

    # индекс: берёт только хорошие, отсортирован
    clean = tempfile.mkdtemp()
    make(clean, 'b-model', vendor='zyxel'); make(clean, 'a-model', vendor='asus'); make(clean, 'broken', vendor='asus', meta={'kind': 'toaster'})
    idx, bad = build_index.build(clean)
    check('индекс: 2 хороших, плохая пропущена', idx['count'] == 2 and bad == [os.path.join('models', 'asus', 'broken')], (idx['count'], bad))
    check('индекс отсортирован по производителю', [m['vendor'] for m in idx['models']] == ['TP-Link', 'TP-Link'] and [m['id'] for m in idx['models']] == ['a-model', 'b-model'], idx['models'])
    check('в индексе нет лишнего (только данные для списка)', all(set(m) <= {'id', 'path', 'vendor', 'model', 'title', 'kind', 'ports', 'photo', 'model3d', 'license', 'author', 'notes'} for m in idx['models']))
    shutil.rmtree(clean, ignore_errors=True)
finally:
    shutil.rmtree(tmp, ignore_errors=True)

print('\n' + ('ВСЁ OK' if not BAD else 'ОШИБКИ: ' + ', '.join(BAD)) + f'  (проверок: {N})')
sys.exit(1 if BAD else 0)
