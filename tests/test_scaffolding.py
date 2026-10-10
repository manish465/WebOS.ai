import sys
from pathlib import Path

def test_python_version():
    """Verify that Python version is 3.11 or higher."""
    assert sys.version_info >= (3, 11), f"Python 3.11+ required, got {sys.version}"

def test_package_imports():
    """Verify that the core WebOS.ai package and all submodules import cleanly."""
    import webos
    import webos.browser
    import webos.storage
    import webos.gateway

    assert hasattr(webos, "__version__")
    assert webos.__version__ == "0.1.0"

def test_directory_structure():
    """Verify that expected module directories exist."""
    root = Path(__file__).parent.parent
    assert (root / "src").is_dir()
    assert (root / "src" / "webos").is_dir()
    assert (root / "src" / "webos" / "browser").is_dir()
    assert (root / "src" / "webos" / "storage").is_dir()
    assert (root / "src" / "webos" / "gateway").is_dir()
    assert (root / "tests").is_dir()
