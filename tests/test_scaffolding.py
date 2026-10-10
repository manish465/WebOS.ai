import sys
from pathlib import Path

def test_python_version():
    """Verify that Python version is 3.11 or higher."""
    assert sys.version_info >= (3, 11), f"Python 3.11+ required, got {sys.version}"

def test_package_imports():
    """Verify that the core WebOS.ai package and all submodules import cleanly."""
    import src
    import src.browser
    import src.storage
    import src.gateway

    assert hasattr(src, "__version__")
    assert src.__version__ == "0.1.0"

def test_directory_structure():
    """Verify that expected module directories exist."""
    root = Path(__file__).parent.parent
    assert (root / "src").is_dir()
    assert (root / "src" / "browser").is_dir()
    assert (root / "src" / "storage").is_dir()
    assert (root / "src" / "gateway").is_dir()
    assert (root / "tests").is_dir()
