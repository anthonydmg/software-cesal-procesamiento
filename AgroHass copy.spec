# -*- mode: python ; coding: utf-8 -*-
from PyInstaller.utils.hooks import collect_all
datas_yolo, binaries_yolo, hiddenimports_yolo = collect_all('ultralytics')

block_cipher = None

a = Analysis(
    ['main.py'],
    pathex=[],
    binaries=[],
    datas=datas_yolo + [
        # --- AQUÍ AGREGAS TUS CARPETAS ---
        # (Ruta origen en tu proyecto, Ruta destino en la carpeta final)
        
        ('assets', 'assets'),  # Copia toda la carpeta assets
        
        # OJO: Si dentro de 'views' o 'core' tienes archivos NO python 
        # (como archivos .ui, .json o el modelo .pt), agrégalos también:
        # ('core/modelos', 'core/modelos'), 
    ],
    hiddenimports=hiddenimports_yolo + [
        # Si usas importaciones dinámicas en core/ o views/, ponlas aquí
    ],
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[],
    optimize=0,
    win_no_prefer_redirects=False,
    win_private_assemblies=False,
    cipher=block_cipher,
)
pyz = PYZ(a.pure)

exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name='AgroHass',
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    console=False,
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
)
coll = COLLECT(
    exe,
    a.binaries,
    a.datas,
    strip=False,
    upx=True,
    upx_exclude=[],
    name='AgroHass',
)
