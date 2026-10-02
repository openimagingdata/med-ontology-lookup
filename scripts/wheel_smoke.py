"""Verify the built wheel in a fresh environment outside the source checkout."""

from __future__ import annotations

import os
import subprocess
import sys
import tempfile
from pathlib import Path


def main() -> None:
    project = Path(__file__).resolve().parents[1]
    wheels = list((project / "dist").glob("*.whl"))
    if len(wheels) != 1:
        raise SystemExit(f"Expected exactly one wheel in dist, found {len(wheels)}")

    env = dict(os.environ)
    env.pop("PYTHONPATH", None)
    env.pop("PYTHONHOME", None)
    with tempfile.TemporaryDirectory(prefix="molu-wheel-smoke-") as directory:
        temporary = Path(directory)
        requirements = temporary / "requirements.txt"
        subprocess.run(
            [
                "uv",
                "export",
                "--locked",
                "--no-dev",
                "--no-emit-project",
                "--format",
                "requirements-txt",
                "--output-file",
                str(requirements),
            ],
            cwd=project,
            env=env,
            check=True,
            stdout=subprocess.DEVNULL,
        )
        venv = temporary / "venv"
        subprocess.run(
            ["uv", "venv", "--python", sys.executable, str(venv)],
            cwd=temporary,
            env=env,
            check=True,
        )
        binaries = venv / ("Scripts" if os.name == "nt" else "bin")
        python = binaries / ("python.exe" if os.name == "nt" else "python")
        subprocess.run(
            ["uv", "pip", "sync", "--python", str(python), "--require-hashes", str(requirements)],
            cwd=temporary,
            env=env,
            check=True,
        )
        subprocess.run(
            ["uv", "pip", "install", "--python", str(python), "--no-deps", str(wheels[0])],
            cwd=temporary,
            env=env,
            check=True,
        )
        subprocess.run(
            [
                str(python),
                "-I",
                "-c",
                (
                    "from pathlib import Path; import sys; import med_ontology_lookup as package; "
                    "assert Path(package.__file__).resolve().is_relative_to(Path(sys.prefix)); "
                    "print(package.__file__)"
                ),
            ],
            cwd=temporary,
            env=env,
            check=True,
        )
        cli = binaries / ("molu.exe" if os.name == "nt" else "molu")
        subprocess.run([str(cli), "--help"], cwd=temporary, env=env, check=True)
        subprocess.run([str(cli), "version"], cwd=temporary, env=env, check=True)


if __name__ == "__main__":
    main()
