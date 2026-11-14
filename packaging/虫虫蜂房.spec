# -*- mode: python ; coding: utf-8 -*-
"""PyInstaller 打包配置（相对路径版，换台机器也能用）。

用法（在仓库根目录）：
    pip install pillow pyinstaller
    python -m PyInstaller --noconfirm packaging\\虫虫蜂房.spec
产物：dist\\虫虫蜂房\\虫虫蜂房.exe 和 dist\\虫虫蜂房\\_internal\\
"""

import os

ROOT = os.path.abspath(os.path.join(SPECPATH, ".."))          # noqa: F821
ASSETS = os.path.join(ROOT, "hive", "assets")

a = Analysis(
    [os.path.join(ROOT, "main.py")],
    pathex=[ROOT],
    binaries=[],
    datas=[(ASSETS, "hive/assets")],                          # 棋子图标、规则图、icon
    hiddenimports=["PIL._tkinter_finder"],
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=["numpy", "scipy", "matplotlib"],                # 用不到，排掉能小一圈
    noarchive=False,
    optimize=0,
)
pyz = PYZ(a.pure)

exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name="虫虫蜂房",
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    console=False,                                            # 双击不弹黑框
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
    icon=os.path.join(ASSETS, "hive.ico"),
)
coll = COLLECT(
    exe,
    a.binaries,
    a.datas,
    strip=False,
    upx=True,
    upx_exclude=[],
    name="虫虫蜂房",
)
