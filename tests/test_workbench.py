import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest

from tools.workbench import allowed, check, context


ROOT = Path(__file__).resolve().parents[1]


class WorkbenchTests(unittest.TestCase):
    def setUp(self):
        self.vault = ROOT / 'demo-vault'
        self.response = json.loads((ROOT / 'examples/good-response.json').read_text(encoding='utf-8'))

    def test_valid_evidence(self):
        self.assertEqual(check(self.vault, self.response), [])

    def test_expected_project_matching_and_mismatching(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            arena = root / 'work/projects/arena/source.md'
            other = root / 'work/projects/other/source.md'
            arena.parent.mkdir(parents=True)
            other.parent.mkdir(parents=True)
            arena.write_text('Arena fact.', encoding='utf-8')
            other.write_text('Other fact.', encoding='utf-8')
            response = {
                'claims': [{'text': 'Arena fact', 'source': 'work/projects/arena/source.md',
                            'quote': 'Arena fact.'}],
                'unknowns': [],
            }
            self.assertEqual(check(root, response, expected_project='arena'), [])
            response['claims'][0]['source'] = 'work/projects/other/source.md'
            response['claims'][0]['quote'] = 'Other fact.'
            errors = check(root, response, expected_project='arena')
            self.assertIn('claim 0: invalid source', errors)
            # Omitting the new option retains the pre-existing behavior.
            self.assertEqual(check(root, response), [])

    def test_expected_project_rejects_invalid_slug(self):
        for slug in ('../arena', 'Arena', 'arena/', '', 3):
            with self.subTest(slug=slug), self.assertRaises(ValueError):
                check(self.vault, self.response, expected_project=slug)

    def test_expected_project_rejects_resolved_path_tricks(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            source = root / 'work/projects/other/source.md'
            source.parent.mkdir(parents=True)
            source.write_text('Other fact.', encoding='utf-8')
            response = {
                'claims': [{'text': 'Other fact',
                            'source': 'work/projects/arena/../other/source.md',
                            'quote': 'Other fact.'}],
                'unknowns': [],
            }
            self.assertTrue(check(root, response, expected_project='arena'))

    def test_check_cli_project_flag(self):
        response_path = ROOT / 'examples/good-response.json'
        script = ROOT / 'tools/workbench.py'
        result = subprocess.run(
            [sys.executable, str(script), 'check', str(self.vault), str(response_path),
             '--project', 'arena'],
            capture_output=True, text=True, check=False,
        )
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertTrue(json.loads(result.stdout)['passed'])

    def test_context_cli_rejects_project_flag_without_sources(self):
        script = ROOT / 'tools/workbench.py'
        result = subprocess.run(
            [sys.executable, str(script), 'context', str(self.vault), 'arena',
             '--project', 'another'],
            capture_output=True, text=True, check=False,
        )
        self.assertNotEqual(result.returncode, 0)
        output = json.loads(result.stdout)
        self.assertIn('error', output)
        self.assertNotIn('sources', output)

    def test_invented_quote(self):
        self.response['claims'][0]['quote'] = 'Production uses MongoDB.'
        self.assertTrue(check(self.vault, self.response))

    def test_path_escape(self):
        for path in ('../../README.md', 'private/secret.md', 'work/projects/../../private/secret.md'):
            with self.subTest(path=path), self.assertRaises(ValueError):
                allowed(self.vault, path)

    def test_hidden_and_private_files(self):
        with tempfile.TemporaryDirectory() as temp:
            for name in ('.hidden', 'private'):
                file = Path(temp) / 'work/projects/arena' / name / 'note.md'
                file.parent.mkdir(parents=True)
                file.write_text('fixture', encoding='utf-8')
                with self.assertRaises(ValueError):
                    allowed(temp, file.relative_to(temp))

    def test_malformed_schema(self):
        for value in ([], {}, {'claims': [None], 'unknowns': []}):
            self.assertTrue(check(self.vault, value))

    def test_credential_pattern(self):
        self.response['unknowns'] = ['password=synthetic-example']
        self.assertTrue(check(self.vault, self.response))

    def test_context_sources(self):
        result = context(self.vault, 'arena')
        self.assertEqual(len(result['sources']), 2)
        self.assertGreater(result['characters'], 0)

    def test_slug_escape(self):
        with self.assertRaises(ValueError):
            context(self.vault, '../arena')

    def test_budget(self):
        with tempfile.TemporaryDirectory() as temp:
            file = Path(temp) / 'work/projects/arena/large.md'
            file.parent.mkdir(parents=True)
            file.write_text('x' * 64_001, encoding='utf-8')
            with self.assertRaises(ValueError):
                context(temp, 'arena')


if __name__ == '__main__':
    unittest.main()
