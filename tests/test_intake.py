"""Безопасная распаковка заявки (tools/intake.py): обычный архив проходит, «zip slip» и чужие файлы — нет. Запуск: python tests/test_intake.py"""
import io, json, os, shutil, sys, tempfile, zipfile

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, 'tools'))
import intake, validate
from PIL import Image, ImageDraw

BAD, N = [], 0


def check(name, ok, extra=''):
    global N
    N += 1
    print(('  ok   ' if ok else '  FAIL ') + name + ('' if ok or not extra else ' — ' + str(extra)))
    if not ok:
        BAD.append(name)


def zipped(files):
    b = io.BytesIO()
    with zipfile.ZipFile(b, 'w') as z:
        for n, d in files.items():
            z.writestr(n, d)
    return b.getvalue()


def refused(blob, dest):
    try:
        intake.extract(blob, dest)
        return None
    except intake.Refuse as e:
        return str(e)


im = Image.new('RGBA', (900, 160), (0, 0, 0, 0)); ImageDraw.Draw(im).rectangle([20, 20, 880, 140], fill=(60, 64, 70, 255))
pb = io.BytesIO(); im.save(pb, 'WEBP')
model = json.dumps({'format': 'racklive-card', 'version': 1, 'id': 'zyxel-demo', 'vendor': 'Zyxel', 'model': 'DEMO', 'kind': 'switch',
                    'photo': {'file': 'photo.webp', 'license': 'own'}, 'spots': [{'n': 1, 'x': .2, 'y': .5, 'w': .04, 'h': .3}]})
good = {'models/zyxel/zyxel-demo/model.json': model, 'models/zyxel/zyxel-demo/photo.webp': pb.getvalue()}
tmp = tempfile.mkdtemp()
try:
    d = os.path.join(tmp, 'a'); os.makedirs(d)
    v, mid, target = intake.extract(zipped(good), d)
    check('хороший архив распаковывается и проходит проверку', (v, mid) == ('zyxel', 'zyxel-demo') and validate.check_dir(target)['ok'])
    check('повторная заявка на ту же модель отклоняется', 'уже есть' in (refused(zipped(good), d) or ''))
    d = os.path.join(tmp, 'b'); os.makedirs(d)
    check('zip slip (../) отклоняется', 'Недопустимый путь' in (refused(zipped({'../evil.py': 'x', **good}), d) or ''))
    check('абсолютный путь отклоняется', 'Недопустимый путь' in (refused(zipped({'/etc/cron.d/x': 'x'}), d) or ''))
    check('скрипт рядом с моделью отклоняется', 'Недопустимый путь' in (refused(zipped({**good, 'models/zyxel/zyxel-demo/run.sh': 'x'}), d) or ''))
    check('две модели в одном архиве отклоняются', 'одна модель' in (refused(zipped({**good, 'models/zyxel/other-model/model.json': '{}'}), d) or ''))
    check('не zip — понятный отказ', 'не zip' in (refused(b'hello', d) or ''))
    check('пустой архив отклоняется', refused(zipped({}), d) is not None)
    check('архив не из каталога models/ отклоняется', 'Недопустимый путь' in (refused(zipped({'model.json': '{}'}), d) or ''))
    check('в d ничего лишнего не появилось', not os.path.exists(os.path.join(d, 'evil.py')) and not os.path.exists(os.path.join(os.path.dirname(d), 'evil.py')))
    check('ссылка находится в тексте заявки', intake.find_url('### Файл\n[a.zip](https://github.com/user-attachments/files/123/a-b.zip)').endswith('a-b.zip'))
    try:
        intake.find_url('[x](https://evil.example/x.zip)'); other = False
    except intake.Refuse:
        other = True
    check('чужая ссылка не принимается', other)
finally:
    shutil.rmtree(tmp, ignore_errors=True)

print('\n' + ('ВСЁ OK' if not BAD else 'ОШИБКИ: ' + ', '.join(BAD)) + f'  (проверок: {N})')
sys.exit(1 if BAD else 0)
