"""Собирает index.json — список моделей для «Магазина» Rack Live. Запуск: python tools/build_index.py
Берёт только те модели, что прошли проверку (tools/validate.py); в индекс попадает минимум: название, тип, число портов, адреса файлов."""
import json, os, sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import validate

ROOT = os.path.dirname(HERE)


def build(root=ROOT):
    items, bad = [], []
    for d in validate.all_dirs(root):
        r = validate.check_dir(d)
        if not r['ok']:
            bad.append(os.path.relpath(d, root))
            continue
        e = r['entry']
        items.append({'id': e['id'], 'path': e['path'], 'vendor': e['vendor'], 'model': e['model'], 'title': e['title'], 'kind': e['kind'],
                      'ports': e['ports'], 'photo': e['photo'], 'model3d': e['model3d'], 'license': e['license'], 'author': e.get('author') or '',
                      'notes': e['notes']})
    items.sort(key=lambda x: (x['vendor'].lower(), x['model'].lower()))
    return {'format': 'racklive-models-index', 'version': 1, 'count': len(items), 'models': items}, bad


if __name__ == '__main__':
    idx, bad = build()
    with open(os.path.join(ROOT, 'index.json'), 'w', encoding='utf-8', newline='\n') as f:
        json.dump(idx, f, ensure_ascii=False, indent=1)
        f.write('\n')
    print(f'index.json: {idx["count"]} моделей' + (f'; пропущены с ошибками: {", ".join(bad)}' if bad else ''))
    sys.exit(1 if bad else 0)
