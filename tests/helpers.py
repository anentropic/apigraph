from pathlib import Path
from typing import Dict


def fixture_uri(rel_path: str) -> str:
    path = Path(__file__).parent / Path("fixtures") / Path(rel_path)
    return f"file://{path}"


def str_doc_with_substitutions(rel_path: str, substitutions: Dict[str, str]) -> str:
    with open(rel_path) as f:
        content = f.read()
    return content.format(**substitutions)
