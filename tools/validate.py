"""Проверка моделей каталога Rack Live. Запуск: python tools/validate.py [папка_модели …]  (без аргументов — все модели в models/).

Модель — это папка models/<производитель>/<id>/ с файлами:
  model.json    описание (обязательно)
  photo.webp | photo.png   фото устройства на ПРОЗРАЧНОМ фоне (по желанию, если есть model3d.json)
  model3d.json  3D-модель формата racklive-model (по желанию, если есть фото)
Больше в папке не должно быть ничего. Данные — только данные: ни кода, ни ссылок для загрузки. Правила здесь те же, что в Rack Live.
Выход 0 — всё хорошо, 1 — есть ошибки (их текст понятен автору заявки)."""
import io, json, os, re, struct, sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import rl_models3d as m3d                      # копия rackd/models.py из Rack Live: те же правила для 3D-моделей

FORMAT, VERSION = 'racklive-card', 1
KINDS = ('router', 'switch', 'server', 'nas', 'ap', 'camera', 'nvr', 'ups', 'pc', 'modem', 'other')
PORT_KINDS = ('rj45', 'sfp', 'usb', 'power', 'console', 'other')
LICENSES = {
    'own': 'моё фото',
    'CC0-1.0': 'CC0 (общественное достояние)',
    'CC-BY-4.0': 'CC BY 4.0 (нужен автор)',
    'CC-BY-SA-4.0': 'CC BY-SA 4.0 (нужен автор)',
    'permission': 'есть разрешение правообладателя',
}
NEED_AUTHOR = ('CC-BY-4.0', 'CC-BY-SA-4.0')
ID_RE = re.compile(r'^[a-z0-9][a-z0-9-]{2,60}$')
VENDOR_RE = re.compile(r'^[a-z0-9][a-z0-9-]{1,40}$')
ALLOWED_FILES = {'model.json', 'photo.webp', 'photo.png', 'model3d.json'}
TOP_KEYS = {'format', 'version', 'id', 'vendor', 'model', 'kind', 'title', 'notes', 'photo', 'spots', 'pzoom', 'model3d'}
PHOTO_KEYS = {'file', 'license', 'author', 'source'}
SPOT_KEYS = {'n', 'x', 'y', 'w', 'h', 'kind', 'label'}
MAX_PHOTO_BYTES, MIN_SIDE, MAX_SIDE = 600 * 1024, 600, 1600
MAX_SPOTS, MAX_JSON = 200, 100_000
CTRL = re.compile(r'[\x00-\x08\x0b\x0c\x0e-\x1f\x7f]')


def _text(v, where, maxlen, errors, required=False):
    if v is None or v == '':
        if required:
            errors.append(f'{where}: заполните')
        return ''
    if not isinstance(v, str):
        errors.append(f'{where}: нужен текст')
        return ''
    if len(v) > maxlen:
        errors.append(f'{where}: длиннее {maxlen} символов')
    if CTRL.search(v):
        errors.append(f'{where}: служебные символы недопустимы')
    return v.strip()


def _num(v, lo, hi):
    return isinstance(v, (int, float)) and not isinstance(v, bool) and lo <= v <= hi


def _png_has_exif(blob):
    i = 8
    while i + 8 <= len(blob):
        ln, typ = struct.unpack('>I4s', blob[i:i + 8])
        if typ == b'eXIf':
            return True
        i += 12 + ln
    return False


def check_photo(path, ext, errors, warnings):
    """→ PIL-картинка RGBA или None"""
    try:
        from PIL import Image
    except ImportError:
        errors.append('на сервере проверки нет Pillow (pip install pillow)')
        return None
    size = os.path.getsize(path)
    if size > MAX_PHOTO_BYTES:
        errors.append(f'photo: файл {size // 1024} КБ, а можно не больше {MAX_PHOTO_BYTES // 1024} КБ — уменьшите в редакторе')
    blob = open(path, 'rb').read()
    magic_ok = (blob[:8] == b'\x89PNG\r\n\x1a\n') if ext == 'png' else (blob[:4] == b'RIFF' and blob[8:12] == b'WEBP')
    if not magic_ok:
        errors.append(f'photo: файл не является настоящим {ext.upper()} (расширение не совпадает с содержимым)')
        return None
    try:
        im = Image.open(io.BytesIO(blob))
        im.load()
    except Exception as e:
        errors.append(f'photo: не открывается ({type(e).__name__})')
        return None
    if getattr(im, 'is_animated', False) and im.n_frames > 1:
        errors.append('photo: анимация не допускается — нужна одна картинка')
    try:
        has_exif = bool(im.getexif()) or (ext == 'png' and _png_has_exif(blob)) or (ext == 'webp' and b'EXIF' in blob[:200000])
    except Exception:
        has_exif = False
    if has_exif:
        errors.append('photo: в файле остались метаданные (EXIF: геопозиция, серийный номер камеры). Пересохраните через редактор — он их убирает')
    w, h = im.size
    if max(w, h) > MAX_SIDE:
        errors.append(f'photo: {w}×{h} — длинная сторона не больше {MAX_SIDE} px')
    if max(w, h) < MIN_SIDE:
        errors.append(f'photo: {w}×{h} — длинная сторона не меньше {MIN_SIDE} px, иначе порты не разглядеть')
    if 'A' not in im.getbands() and im.mode not in ('P', 'LA', 'RGBa', 'La'):
        errors.append('photo: фон не прозрачный (нет альфа-канала). Нужен PNG или WebP с прозрачным фоном — в редакторе есть «Убрать фон»')
        return None
    im = im.convert('RGBA')
    a = im.getchannel('A')
    px = a.load()
    ring = [px[x, y] for x in range(w) for y in (0, 1, h - 2, h - 1)] + [px[x, y] for y in range(h) for x in (0, 1, w - 2, w - 1)]
    clear = sum(1 for v in ring if v <= 8) / len(ring)
    if clear < .97:
        errors.append(f'photo: фон не прозрачный — у краёв снимка прозрачно только {round(clear * 100)}% (нужно 97%+). Оставьте вокруг устройства прозрачное поле и уберите фон')
    solid = sum(1 for v in a.getdata() if v > 200) / (w * h)
    if solid < .05:
        errors.append('photo: почти всё изображение прозрачное — устройства на нём не видно')
    elif solid > .985:
        errors.append('photo: фон не прозрачный — изображение целиком непрозрачное')
    return im


def check_dir(d):
    """→ {'ok', 'errors', 'warnings', 'entry'} для папки модели"""
    errors, warnings = [], []
    d = os.path.abspath(d)
    mid, vendor_dir = os.path.basename(d), os.path.basename(os.path.dirname(d))
    if not ID_RE.match(mid):
        errors.append(f'папка «{mid}»: имя только из строчных латинских букв, цифр и дефисов (3–61 символ)')
    if not VENDOR_RE.match(vendor_dir):
        errors.append(f'папка производителя «{vendor_dir}»: только строчные латинские буквы, цифры и дефисы')
    files = os.listdir(d)
    for f in files:
        if f not in ALLOWED_FILES:
            errors.append(f'лишний файл «{f}»: в папке могут быть только {", ".join(sorted(ALLOWED_FILES))}')
    for f in files:
        if os.path.islink(os.path.join(d, f)):
            errors.append(f'«{f}»: ссылки (symlink) недопустимы')
    mp = os.path.join(d, 'model.json')
    if not os.path.isfile(mp):
        return {'ok': False, 'errors': errors + ['нет файла model.json'], 'warnings': warnings, 'entry': None}
    if os.path.getsize(mp) > MAX_JSON:
        return {'ok': False, 'errors': errors + [f'model.json больше {MAX_JSON // 1000} КБ'], 'warnings': warnings, 'entry': None}
    try:
        m = json.load(open(mp, encoding='utf-8'))
    except (ValueError, UnicodeDecodeError) as e:
        return {'ok': False, 'errors': errors + [f'model.json: это не JSON ({e})'], 'warnings': warnings, 'entry': None}
    if not isinstance(m, dict):
        return {'ok': False, 'errors': errors + ['model.json: нужен объект { … }'], 'warnings': warnings, 'entry': None}
    for k in m:
        if k not in TOP_KEYS:
            errors.append(f'model.json: неизвестное поле «{k}»')
    if m.get('format') != FORMAT:
        errors.append(f'format: должно быть "{FORMAT}"')
    if m.get('version') != VERSION:
        errors.append(f'version: должно быть {VERSION}')
    if m.get('id') != mid:
        errors.append(f'id: должно совпадать с именем папки («{mid}»)')
    vendor = _text(m.get('vendor'), 'vendor', 40, errors, True)
    model = _text(m.get('model'), 'model', 60, errors, True)
    title = _text(m.get('title'), 'title', 100, errors) or (vendor + ' ' + model).strip()
    notes = _text(m.get('notes'), 'notes', 300, errors)
    kind = m.get('kind')
    if kind not in KINDS:
        errors.append(f'kind: одно из {", ".join(KINDS)}')

    entry = {'id': mid, 'path': f'models/{vendor_dir}/{mid}', 'vendor': vendor, 'model': model, 'title': title, 'kind': kind, 'notes': notes,
             'ports': 0, 'photo': None, 'model3d': False, 'license': None}
    ph = m.get('photo')
    im = None
    if ph is not None:
        if not isinstance(ph, dict):
            errors.append('photo: нужен объект {file, license, author, source}')
        else:
            for k in ph:
                if k not in PHOTO_KEYS:
                    errors.append(f'photo: неизвестное поле «{k}»')
            fn = ph.get('file')
            if fn not in ('photo.webp', 'photo.png'):
                errors.append('photo.file: «photo.webp» или «photo.png»')
            elif not os.path.isfile(os.path.join(d, fn)):
                errors.append(f'photo.file: файла «{fn}» нет в папке')
            else:
                im = check_photo(os.path.join(d, fn), fn.rsplit('.', 1)[1], errors, warnings)
                entry['photo'] = fn
            lic = ph.get('license')
            if lic not in LICENSES:
                errors.append('photo.license: одно из ' + ', '.join(LICENSES))
            else:
                entry['license'] = lic
            author = _text(ph.get('author'), 'photo.author', 80, errors)
            source = _text(ph.get('source'), 'photo.source', 300, errors)
            if lic in NEED_AUTHOR and not author:
                errors.append('photo.author: для этой лицензии нужно указать автора')
            if lic not in (None, 'own') and not source:
                errors.append('photo.source: укажите, откуда фото (адрес страницы или описание разрешения)')
            if source and not re.match(r'^https://[^\s<>"]+$', source) and lic != 'permission':
                errors.append('photo.source: адрес должен начинаться с https://')
            entry['author'] = author
    spots = m.get('spots')
    clean_spots = []
    if spots is not None:
        if not isinstance(spots, list) or len(spots) > MAX_SPOTS:
            errors.append(f'spots: список не длиннее {MAX_SPOTS}')
        else:
            seen = set()
            for i, s in enumerate(spots):
                w = f'spots[{i}]'
                if not isinstance(s, dict):
                    errors.append(f'{w}: нужен объект')
                    continue
                for k in s:
                    if k not in SPOT_KEYS:
                        errors.append(f'{w}: неизвестное поле «{k}»')
                n = s.get('n')
                if not (isinstance(n, int) and not isinstance(n, bool) and 1 <= n <= 256):
                    errors.append(f'{w}.n: номер порта 1…256')
                elif n in seen:
                    errors.append(f'{w}.n: порт {n} указан дважды')
                else:
                    seen.add(n)
                if not (_num(s.get('x'), 0, 1) and _num(s.get('y'), 0, 1)):
                    errors.append(f'{w}: x и y — число 0…1 (центр порта в долях фото)')
                if not (_num(s.get('w'), 0.002, .6) and _num(s.get('h'), 0.002, .6)):
                    errors.append(f'{w}: w и h — число 0.002…0.6 (размер порта в долях фото)')
                if s.get('kind') is not None and s['kind'] not in PORT_KINDS:
                    errors.append(f'{w}.kind: одно из {", ".join(PORT_KINDS)}')
                _text(s.get('label'), f'{w}.label', 24, errors)
                clean_spots.append(s)
            if clean_spots and ph is None:
                errors.append('spots: точки портов относятся к фото, а фото в заявке нет')
            if im is not None:
                W, H = im.size
                a = im.getchannel('A').load()
                for s in clean_spots:
                    if _num(s.get('x'), 0, 1) and _num(s.get('y'), 0, 1) and isinstance(s.get('n'), int):
                        if a[min(W - 1, int(s['x'] * W)), min(H - 1, int(s['y'] * H))] < 20:
                            warnings.append(f'порт {s["n"]}: точка стоит на прозрачном месте, а не на устройстве')
        entry['ports'] = len(clean_spots)
    pz = m.get('pzoom')
    if pz is not None:
        if not (isinstance(pz, dict) and set(pz) == {'x', 'y', 'w', 'h'} and _num(pz['x'], 0, 1) and _num(pz['y'], 0, 1) and _num(pz['w'], .02, 1) and _num(pz['h'], .02, 1)
                and pz['x'] + pz['w'] <= 1.0001 and pz['y'] + pz['h'] <= 1.0001):
            errors.append('pzoom: {x, y, w, h} — прямоугольник приближения в долях фото (x, y — левый верхний угол), целиком внутри фото')
        elif ph is None:
            errors.append('pzoom: приближение относится к фото, а фото в заявке нет')
    if m.get('model3d') is not None:
        if m['model3d'] != 'model3d.json':
            errors.append('model3d: «model3d.json»')
        elif not os.path.isfile(os.path.join(d, 'model3d.json')):
            errors.append('model3d: файла model3d.json нет в папке')
        else:
            clean, errs = m3d.validate(open(os.path.join(d, 'model3d.json'), encoding='utf-8').read())
            if errs:
                errors += [f'model3d.json: {e}' for e in errs]
            else:
                entry['model3d'] = True
                entry['ports3d'] = sum(1 for f in clean['faces'].values() for it in f.get('items', []) if it.get('type') == 'port')
    if ph is None and m.get('model3d') is None:
        errors.append('нужно хотя бы одно: фото (photo) или 3D-модель (model3d)')
    if os.path.isfile(os.path.join(d, 'model3d.json')) and m.get('model3d') is None:
        errors.append('model3d.json есть в папке, но не указан в model.json (поле model3d)')
    return {'ok': not errors, 'errors': errors, 'warnings': warnings, 'entry': entry if not errors else None}


def all_dirs(root):
    base = os.path.join(root, 'models')
    out = []
    if os.path.isdir(base):
        for v in sorted(os.listdir(base)):
            vp = os.path.join(base, v)
            if os.path.isdir(vp):
                out += [os.path.join(vp, i) for i in sorted(os.listdir(vp)) if os.path.isdir(os.path.join(vp, i))]
    return out


def main(argv):
    root = os.path.dirname(HERE)
    dirs = argv or all_dirs(root)
    bad = 0
    for d in dirs:
        r = check_dir(d)
        name = os.path.relpath(d, root) if os.path.abspath(d).startswith(root) else d
        print(('OK    ' if r['ok'] else 'ОШИБКА ') + name)
        for e in r['errors']:
            print('   ✗ ' + e)
        for w in r['warnings']:
            print('   ! ' + w)
        bad += 0 if r['ok'] else 1
    print(f'\nмоделей: {len(dirs)}, с ошибками: {bad}')
    return 1 if bad else 0


if __name__ == '__main__':
    sys.exit(main(sys.argv[1:]))
