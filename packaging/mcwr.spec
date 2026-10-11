# PyInstaller spec (onedir) for Markdown Card Whiteboard Reader.
#
# Build:  python -m uv run pyinstaller packaging/mcwr.spec --noconfirm
# Check:  dist/mcwr/mcwr.exe --self-check        (opens a generated document, renders the
#         math and mermaid cards, prints a JSON summary, exits non-zero on failure)
#
# onedir is deliberate (NFR-7): it starts faster and trips fewer antivirus heuristics than
# onefile. The web assets (KaTeX + Mermaid, ~5.9 MB) are data files, not code, so they are
# shipped verbatim and found at runtime through mcwr.infrastructure.app_paths.assets_dir().

from pathlib import Path

REPO = Path(SPECPATH).parent  # noqa: F821 - SPECPATH is provided by PyInstaller
ASSETS = REPO / "src" / "mcwr" / "assets"

a = Analysis(  # noqa: F821
    [str(REPO / "packaging" / "entry_gui.py")],
    pathex=[str(REPO / "src")],
    binaries=[],
    datas=[(str(ASSETS), "mcwr/assets")],
    hiddenimports=[
        "mcwr.infrastructure.web_renderer",
        "mcwr.infrastructure.markdown_it_adapter",
        "mdit_py_plugins.dollarmath",
        "mdit_py_plugins.tasklists",
    ],
    hookspath=[],
    runtime_hooks=[],
    # QtWebEngine ships its own process binaries; excluding PySide6's unused heavy modules
    # keeps the bundle small. NOTE: QtWebEngineWidgets imports QtWebChannel (and QtWebEngine
    # drags in Qml/Quick), so those must stay — excluding QtWebChannel made the frozen app
    # fail with "ImportError: libshiboken: could not import module 'PySide6.QtWebChannel'"
    # and every math/mermaid card silently fell back to text.
    excludes=[
        "PySide6.Qt3DAnimation",
        "PySide6.Qt3DCore",
        "PySide6.Qt3DExtras",
        "PySide6.Qt3DInput",
        "PySide6.Qt3DLogic",
        "PySide6.Qt3DRender",
        "PySide6.QtBluetooth",
        "PySide6.QtCharts",
        "PySide6.QtDataVisualization",
        "PySide6.QtDesigner",
        "PySide6.QtMultimedia",
        "PySide6.QtMultimediaWidgets",
        "PySide6.QtNetworkAuth",
        "PySide6.QtNfc",
        "PySide6.QtPositioning",
        "PySide6.QtQuick3D",
        "PySide6.QtRemoteObjects",
        "PySide6.QtScxml",
        "PySide6.QtSensors",
        "PySide6.QtSerialPort",
        "PySide6.QtSpatialAudio",
        "PySide6.QtSql",
        "PySide6.QtStateMachine",
        "PySide6.QtTest",
        "PySide6.QtTextToSpeech",
        "tkinter",
    ],
    noarchive=False,
)

pyz = PYZ(a.pure)  # noqa: F821

exe = EXE(  # noqa: F821
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name="mcwr",
    debug=False,
    strip=False,
    upx=False,
    console=False,  # GUI subsystem: never flash a console window (pitfall §13.15)
    icon=None,
)

coll = COLLECT(  # noqa: F821
    exe,
    a.binaries,
    a.datas,
    strip=False,
    upx=False,
    name="mcwr",
)
