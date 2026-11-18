"""PyInstaller-safe absolute import launcher for offline Windows CLI."""
from reqea.cli import main

if __name__ == "__main__":
    raise SystemExit(main())
