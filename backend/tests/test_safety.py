"""Guards against signing libraries and secret material landing in the tree."""

import ast
import re
from pathlib import Path

from hypergrok.logging_config import redact

REPO = Path(__file__).resolve().parents[2]
PACKAGE = REPO / "backend" / "hypergrok"
FORBIDDEN_MODULES = {
    "eth_account",
    "web3",
    "solders",
    "solana",
    "nacl",
    "coincurve",
    "bip_utils",
    "hdwallet",
    "mnemonic",
    "bitcoinlib",
}
SECRET_ASSIGNMENT = re.compile(
    r"(?i)(private[_-]?key|seed[_-]?phrase|mnemonic|api[_-]?key)\s*=\s*['\"][^'\"]+['\"]"
)
HEX_KEY = re.compile(r"0x[a-fA-F0-9]{64}")


def _imported_modules(tree: ast.AST) -> set[str]:
    found: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                found.add(alias.name.split(".")[0])
        elif isinstance(node, ast.ImportFrom) and node.module:
            found.add(node.module.split(".")[0])
    return found


def test_package_does_not_import_signing_libraries() -> None:
    offenders: list[str] = []
    for path in PACKAGE.rglob("*.py"):
        tree = ast.parse(path.read_text(encoding="utf-8"))
        banned = _imported_modules(tree) & FORBIDDEN_MODULES
        if banned:
            offenders.append(f"{path}: {sorted(banned)}")
    assert offenders == []


def test_requirements_and_example_env_have_no_secrets() -> None:
    requirements = (REPO / "requirements.txt").read_text(encoding="utf-8")
    example = (REPO / ".env.example").read_text(encoding="utf-8")
    for label, text in (("requirements", requirements), ("env", example)):
        assert SECRET_ASSIGNMENT.search(text) is None, label
        assert HEX_KEY.search(text) is None, label
        assert "solana" not in requirements.lower()
    for name in FORBIDDEN_MODULES:
        assert name not in requirements


def test_redactor_hides_token_like_fields() -> None:
    cleaned = redact(
        {
            "symbol": "BTC",
            "approval_token": "super-secret",
            "nested": {"private_key": "0xabc", "notional": "1"},
        }
    )
    assert cleaned["symbol"] == "BTC"
    assert cleaned["approval_token"] == "[redacted]"
    assert cleaned["nested"]["private_key"] == "[redacted]"
    assert cleaned["nested"]["notional"] == "1"
