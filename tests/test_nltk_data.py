"""Verified download behavior and optional offline NLTK resource checks."""
import hashlib
import importlib.util
import io
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
import zipfile

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location('prepare_nltk_data', ROOT / 'scripts/prepare_nltk_data.py')
prepare = importlib.util.module_from_spec(spec)
spec.loader.exec_module(prepare)

class DownloadTests(unittest.TestCase):
    def setUp(self):
        self.directory = tempfile.TemporaryDirectory()
        self.addCleanup(self.directory.cleanup)
        self.patch = patch.object(prepare, 'PACKAGE_ROOT', Path(self.directory.name))
        self.patch.start()
        self.addCleanup(self.patch.stop)
        buffer = io.BytesIO()
        with zipfile.ZipFile(buffer, 'w') as archive:
            archive.writestr('synthetic/data.txt', 'synthetic fixture')
        self.data = buffer.getvalue()
        self.digest = hashlib.sha256(self.data).hexdigest()

    def test_download_verifies_and_reuses_existing_archive(self):
        with patch.object(prepare.urllib.request, 'urlopen', return_value=io.BytesIO(self.data)) as open_url:
            prepare.prepare_archive('synthetic.zip', self.digest)
            prepare.prepare_archive('synthetic.zip', self.digest)
        self.assertEqual(open_url.call_count, 1)
        self.assertEqual((prepare.PACKAGE_ROOT / 'synthetic.zip').read_bytes(), self.data)

    def test_bad_download_is_not_saved(self):
        with patch.object(prepare.urllib.request, 'urlopen', return_value=io.BytesIO(b'bad')):
            with self.assertRaisesRegex(ValueError, 'SHA-256'):
                prepare.prepare_archive('synthetic.zip', self.digest)
        self.assertFalse((prepare.PACKAGE_ROOT / 'synthetic.zip').exists())

    def test_existing_mismatched_archive_is_preserved(self):
        destination = prepare.PACKAGE_ROOT / 'synthetic.zip'
        destination.write_bytes(b'user archive')
        with patch.object(prepare.urllib.request, 'urlopen') as open_url:
            with self.assertRaises(ValueError):
                prepare.prepare_archive('synthetic.zip', self.digest)
        open_url.assert_not_called()
        self.assertEqual(destination.read_bytes(), b'user archive')

try:
    import nltk
except ImportError:
    nltk = None

HAS_DATA = all((prepare.PACKAGE_ROOT / path).is_file() for path in prepare.ARCHIVES)

@unittest.skipUnless(nltk is not None and HAS_DATA, 'Install nltk and prepare official local archives')
class OfflineResourceTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.directory = tempfile.TemporaryDirectory()
        cls.addClassCleanup(cls.directory.cleanup)
        cls.old_paths = nltk.data.path[:]
        cls.addClassCleanup(setattr, nltk.data, 'path', cls.old_paths)
        for relative, checksum in prepare.ARCHIVES.items():
            data = (prepare.PACKAGE_ROOT / relative).read_bytes()
            prepare.validate(data, checksum)
            with zipfile.ZipFile(io.BytesIO(data)) as archive:
                archive.extractall(Path(cls.directory.name) / Path(relative).parent)
        nltk.data.path = [cls.directory.name]

    def test_all_archives_match_official_hashes(self):
        for relative, checksum in prepare.ARCHIVES.items():
            with self.subTest(archive=relative):
                prepare.validate((prepare.PACKAGE_ROOT / relative).read_bytes(), checksum)

    def test_sentence_tokenization(self):
        self.assertEqual(nltk.sent_tokenize('Hello. This is synthetic text.'),
                         ['Hello.', 'This is synthetic text.'])

    def test_pronouncing_dictionary(self):
        from nltk.corpus import cmudict
        self.assertIn('hello', cmudict.dict())

    def test_english_pos_tagging(self):
        self.assertEqual(nltk.pos_tag(['Hello', 'world']), [('Hello', 'NNP'), ('world', 'NN')])

if __name__ == '__main__':
    unittest.main()
