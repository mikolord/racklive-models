"""Приём заявки: берёт .zip из текста Issue, безопасно распаковывает, проверяет и открывает pull request (или пишет автору, что исправить).
Запускается GitHub Actions (.github/workflows/submission.yml) на коде из main — присланный код нигде не выполняется, zip — только данные.
Переменные: ISSUE_NUMBER, ISSUE_BODY, ISSUE_AUTHOR, GH_TOKEN (для gh), GITHUB_REPOSITORY."""
import io, json, os, re, shutil, subprocess, sys, urllib.request, zipfile

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import validate

ROOT = os.path.dirname(HERE)
MAX_ZIP, MAX_UNPACKED = 2 * 1024 * 1024, 2 * 1024 * 1024
URL_RE = re.compile(r'https://github\.com/(?:user-attachments/files/\d+|[\w.-]+/[\w.-]+/files/\d+)/[\w.%+-]+\.zip')
NAME_RE = re.compile(r'^models/([a-z0-9][a-z0-9-]{1,40})/([a-z0-9][a-z0-9-]{2,60})/(model\.json|photo\.webp|photo\.png|model3d\.json)$')
HOSTS = ('github.com', 'objects.githubusercontent.com', 'user-images.githubusercontent.com')


class Refuse(Exception):
    """заявку нельзя принять — текст увидит автор"""


def find_url(body):
    m = URL_RE.search(body or '')
    if not m:
        raise Refuse('Не нашёл в заявке файл .zip. Скачайте файл в редакторе и перетащите его в поле «Файл», дождитесь, пока он загрузится, и отправьте заявку заново.')
    return m.group(0)


def download(url):
    class Guard(urllib.request.HTTPRedirectHandler):
        def redirect_request(self, req, fp, code, msg, headers, newurl):
            host = re.match(r'https://([^/]+)/', newurl + '/')
            if not host or host.group(1) not in HOSTS and not host.group(1).endswith('.githubusercontent.com'):
                raise Refuse('Файл лежит на неподдерживаемом адресе')
            return super().redirect_request(req, fp, code, msg, headers, newurl)
    op = urllib.request.build_opener(Guard)
    with op.open(urllib.request.Request(url, headers={'User-Agent': 'racklive-models-intake'}), timeout=30) as r:
        blob = r.read(MAX_ZIP + 1)
    if len(blob) > MAX_ZIP:
        raise Refuse(f'Файл больше {MAX_ZIP // 1024 // 1024} МБ')
    return blob


def extract(blob, dest):
    """безопасная распаковка в dest → (vendor, id). Только models/<производитель>/<id>/{model.json, photo.*, model3d.json}, одна модель на заявку."""
    try:
        z = zipfile.ZipFile(io.BytesIO(blob))
    except zipfile.BadZipFile:
        raise Refuse('Это не zip-архив или он повреждён')
    infos = [i for i in z.infolist() if not i.is_dir()]
    if not infos or len(infos) > 4:
        raise Refuse('В архиве должно быть от 1 до 4 файлов (model.json, фото, model3d.json)')
    dirs, total = set(), 0
    for i in infos:
        m = NAME_RE.match(i.filename)
        if not m:
            raise Refuse(f'Недопустимый путь в архиве: «{i.filename[:80]}». Используйте архив, который собрал редактор')
        if (i.external_attr >> 16) & 0o170000 == 0o120000:
            raise Refuse('В архиве есть символическая ссылка')
        total += i.file_size
        dirs.add((m.group(1), m.group(2)))
    if len(dirs) != 1:
        raise Refuse('В одной заявке — одна модель')
    if total > MAX_UNPACKED or any(i.file_size > MAX_UNPACKED for i in infos):
        raise Refuse('Файлы в архиве слишком большие')
    (vendor, mid), = dirs
    target = os.path.join(dest, 'models', vendor, mid)
    if os.path.exists(target):
        raise Refuse(f'Модель «{mid}» уже есть в каталоге. Чтобы исправить её, откройте обычный pull request или напишите владельцу каталога')
    os.makedirs(target)
    for i in infos:
        with z.open(i) as src, open(os.path.join(dest, *i.filename.split('/')), 'wb') as out:
            out.write(src.read(MAX_UNPACKED + 1))
    return vendor, mid, target


def gh(*args, check=True):
    return subprocess.run(['gh', *args], check=check, capture_output=True, text=True)


def git(*args):
    return subprocess.run(['git', *args], check=True, capture_output=True, text=True).stdout.strip()


def main():
    n, body, author = os.environ['ISSUE_NUMBER'], os.environ.get('ISSUE_BODY', ''), os.environ.get('ISSUE_AUTHOR', '')
    report = os.path.join(ROOT, '.intake-report.md')
    try:
        blob = download(find_url(body))
        vendor, mid, target = extract(blob, ROOT)
        res = validate.check_dir(target)
        if not res['ok']:
            shutil.rmtree(target, ignore_errors=True)
            raise Refuse('Модель не прошла проверку:\n\n' + '\n'.join('- ' + e for e in res['errors']) + '\n\nИсправьте это в редакторе, скачайте новый файл и отправьте новую заявку.')
        e = res['entry']
        lines = [f'Заявка #{n} от @{author}', '', f'**{e["title"]}** ({e["vendor"]} {e["model"]}, {e["kind"]})', '',
                 f'- портов отмечено: {e["ports"]}', f'- 3D-модель: {"да" if e["model3d"] else "нет"}', f'- лицензия фото: {e["license"] or "—"}' + (f', автор: {e["author"]}' if e.get('author') else ''),
                 '', 'Автопроверка пройдена.' + ('' if not res['warnings'] else '\n\nПредупреждения:\n' + '\n'.join('- ' + w for w in res['warnings'])), '', f'Closes #{n}']
        open(report, 'w', encoding='utf-8').write('\n'.join(lines))
        branch = f'submission/{n}'
        git('config', 'user.name', 'racklive-models-bot'); git('config', 'user.email', 'racklive-models-bot@users.noreply.github.com')
        git('checkout', '-b', branch); git('add', 'models'); git('commit', '-m', f'Модель: {e["title"]} (заявка #{n})'); git('push', 'origin', branch)
        pr = gh('pr', 'create', '--title', f'Модель: {e["title"]}', '--body-file', report, '--base', 'main', '--head', branch).stdout.strip()
        sha = git('rev-parse', 'HEAD')
        gh('api', f'repos/{os.environ["GITHUB_REPOSITORY"]}/statuses/{sha}', '-f', 'state=success', '-f', 'context=validate', '-f', 'description=Проверка каталога пройдена', check=False)
        gh('issue', 'comment', n, '--body', f'Спасибо! Модель прошла автопроверку, создан pull request: {pr}\nВладелец каталога посмотрит и примет её.')
        gh('issue', 'edit', n, '--add-label', 'checked', check=False)
    except Refuse as e:
        gh('issue', 'comment', n, '--body', str(e))
        gh('issue', 'edit', n, '--add-label', 'needs-fix', check=False)
        print('отказ:', e)
    return 0


if __name__ == '__main__':
    sys.exit(main())
