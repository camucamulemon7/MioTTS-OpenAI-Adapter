"""Prepare verified build inputs from the official NLTK data repository."""
import hashlib
import io
from pathlib import Path
import tempfile
import urllib.request
import zipfile

REVISION = '550b6625bcef1f2abff2ff770a5a0d272c9c6b2a'
BASE_URL = f'https://raw.githubusercontent.com/nltk/nltk_data/{REVISION}/packages'
PACKAGE_ROOT = Path(__file__).resolve().parents[1] / 'local/nltk_data/packages'
# SHA-256 values from the official index.xml at REVISION.
ARCHIVES = {
    'tokenizers/punkt.zip': '51c3078994aeaf650bfc8e028be4fb42b4a0d177d41c012b6a983979653660ec',
    'tokenizers/punkt_tab.zip': 'e57f64187974277726a3417ca6f181ec5403676c717672eef6a748a7b20e0106',
    'taggers/averaged_perceptron_tagger.zip': 'e1f13cf2532daadfd6f3bc481a49859f0b8ea6432ccdcd83e6a49a5f19008de9',
    'taggers/averaged_perceptron_tagger_eng.zip': '6025f530624335c67d6547d44757b357b4e79bae030a0383e9887a92c1718f0b',
    'corpora/cmudict.zip': 'd07cca47fd72ad32ea9d8ad1219f85301eeaf4568f8b6b73747506a71fb5afd6',
}


def validate(data: bytes, expected_hash: str) -> None:
    if hashlib.sha256(data).hexdigest() != expected_hash:
        raise ValueError('NLTK archive SHA-256 mismatch')
    with zipfile.ZipFile(io.BytesIO(data)) as archive:
        if archive.testzip() is not None:
            raise ValueError('NLTK archive ZIP integrity failure')
        for name in archive.namelist():
            if name.startswith('/') or '..' in Path(name).parts:
                raise ValueError('NLTK archive contains an unsafe path')


def prepare_archive(relative_path: str, expected_hash: str) -> None:
    destination = PACKAGE_ROOT / relative_path
    if destination.exists():
        # Do not replace user-provided archives that differ from the pinned set.
        validate(destination.read_bytes(), expected_hash)
        print(f'Verified existing {relative_path}')
        return
    with urllib.request.urlopen(f'{BASE_URL}/{relative_path}', timeout=60) as response:
        data = response.read()
    validate(data, expected_hash)
    destination.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.NamedTemporaryFile(dir=destination.parent, delete=False) as temporary:
        temporary.write(data)
        temporary_path = Path(temporary.name)
    try:
        temporary_path.replace(destination)
    finally:
        temporary_path.unlink(missing_ok=True)
    print(f'Downloaded and verified {relative_path}')


def main() -> None:
    for relative_path, expected_hash in ARCHIVES.items():
        prepare_archive(relative_path, expected_hash)


if __name__ == '__main__':
    main()
