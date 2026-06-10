# -*- mode: python ; coding: utf-8 -*-
from pathlib import Path

root = Path(SPECPATH)

a = Analysis(
    [str(root / "launcher.py")],
    pathex=[str(root)],
    binaries=[],
    datas=[
        (str(root / "templates"), "templates"),
        (str(root / "static"), "static"),
    ],
    hiddenimports=["webview.platforms.edgechromium", "webview.platforms.winforms", "clr"],
    hookspath=[],
    runtime_hooks=[],
    excludes=[],
    noarchive=False,
)
pyz = PYZ(a.pure)
exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name="PIng",
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    console=False,
    icon=str(root / "assets" / "ping.ico"),
    uac_admin=True,
)
coll = COLLECT(exe, a.binaries, a.datas, strip=False, upx=True, name="PIng")
