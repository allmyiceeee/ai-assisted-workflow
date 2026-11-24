import json
from pathlib import Path
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
