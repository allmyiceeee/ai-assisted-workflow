"""Local context packaging and evidence checks. No LLM calls."""
import argparse
import json
from pathlib import Path
import re
import time


def allowed(root, relative):
    root = Path(root).resolve()
    path = (root / relative).resolve()
    base = (root / 'work' / 'projects').resolve()
    if not base.is_relative_to(root) or not path.is_relative_to(base):
        raise ValueError('Source outside allowed project directory')
    parts = path.relative_to(root).parts
    if any(p.startswith('.') or p.lower() == 'private' for p in parts):
        raise ValueError('Hidden or private source')
    if path.suffix != '.md' or not path.is_file():
        raise ValueError('Source must be an existing Markdown file')
    return path


def context(root, slug):
    if not re.fullmatch(r'[a-z0-9]+(?:-[a-z0-9]+)*', slug):
        raise ValueError('Invalid project slug')
    root = Path(root).resolve()
    project = root / 'work' / 'projects' / slug
    files = sorted(project.rglob('*.md'))
    if not files:
        raise ValueError('Project has no sources')
    result = []
    total = 0
    for file in files:
        relative = file.relative_to(root).as_posix()
        source = allowed(root, relative)
        if source.stat().st_size > 64_000:
            raise ValueError('Source exceeds 64 KB budget')
        body = source.read_text(encoding='utf-8')
        total += len(body)
        if total > 100_000:
            raise ValueError('Context exceeds character budget')
        result.append({'source': relative, 'content': body})
    return {'sources': result, 'characters': total}


def check(root, response, expected_project=None):
    project_dir = None
    if expected_project is not None:
        if not isinstance(expected_project, str) or not re.fullmatch(
            r'[a-z0-9]+(?:-[a-z0-9]+)*', expected_project
        ):
            raise ValueError('Invalid project slug')
        root = Path(root).resolve()
        projects_dir = (root / 'work' / 'projects').resolve()
        project_dir = (projects_dir / expected_project).resolve()
        # A project directory must itself be a direct child of the projects
        # directory. This rejects symlink aliases to another project.
        if project_dir.parent != projects_dir or project_dir.name != expected_project:
            raise ValueError('Invalid project directory')
    errors = []
    if not isinstance(response, dict):
        return ['Response must be an object']
    claims = response.get('claims')
    if not isinstance(claims, list) or not claims:
        errors.append('claims must be a nonempty list')
        claims = []
    unknowns = response.get('unknowns')
    if not isinstance(unknowns, list) or any(not isinstance(x, str) for x in unknowns):
        errors.append('unknowns must be a list of strings')
    for i, claim in enumerate(claims):
        if not isinstance(claim, dict) or any(
            not isinstance(claim.get(k), str) or not claim[k].strip()
            for k in ('text', 'source', 'quote')
        ):
            errors.append(f'claim {i}: text, source and quote are required')
            continue
        try:
            source = allowed(root, claim['source'])
            if project_dir is not None and not source.is_relative_to(project_dir):
                raise ValueError('Source belongs to another project')
            if source.stat().st_size > 64_000:
                raise ValueError('Source exceeds budget')
            if claim['quote'] not in source.read_text(encoding='utf-8'):
                errors.append(f'claim {i}: quote not found')
        except (ValueError, OSError):
            errors.append(f'claim {i}: invalid source')
    serialized = json.dumps(response, ensure_ascii=False)
    if re.search(r'(?i)(?:password|api[_-]?key|token)\s*[:=]\s*\S+|-----BEGIN .*PRIVATE KEY-----', serialized):
        errors.append('Possible credential in response')
    return errors


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('command', choices=['context', 'check'])
    parser.add_argument('vault')
    parser.add_argument('target')
    parser.add_argument('--project', help='Require check evidence to come from this project slug')
    args = parser.parse_args()
    started = time.perf_counter()
    try:
        if args.command == 'context':
            if args.project is not None:
                raise ValueError('--project is only valid with the check command')
            result = context(args.vault, args.target)
            status = 0
        else:
            response = json.loads(Path(args.target).read_text(encoding='utf-8'))
            errors = check(args.vault, response, expected_project=args.project)
            result = {'passed': not errors, 'errors': errors}
            status = int(bool(errors))
    except (ValueError, OSError) as exc:
        result, status = {'error': str(exc)}, 1
    result['duration_ms'] = round((time.perf_counter() - started) * 1000, 3)
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return status


if __name__ == '__main__':
    raise SystemExit(main())
