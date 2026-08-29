# -*- mode: python ; coding: utf-8 -*-
"""PyInstaller spec for building the Elodie GUI as a single Windows EXE.

Build with:
    pyinstaller gui_elodie.spec
"""

block_cipher = None

# Qt binary modules (DLLs / binary plugin files) that this pure-Widgets app
# does not need. Kept in a set of file-name stems so the binary collector can
# drop them from a.binaries even though PySide6's hooks pull them in as DLLs
# (a plain `excludes=` entry only removes Python modules, not these binaries).
qt_unused_binaries = (
    'Qt6Qml.dll',
    'Qt6QmlModels.dll',
    'Qt6QmlMeta.dll',
    'Qt6QmlWorkerScript.dll',
    'Qt6Quick.dll',
    'Qt6QuickWidgets.dll',
    'Qt6QuickControls2Impl.dll',
    'Qt6QuickTemplates2.dll',
    'Qt6QuickLayouts.dll',
    'Qt6Pdf.dll',
    'Qt6PdfWidgets.dll',
    'Qt6VirtualKeyboard.dll',
    'Qt6VirtualKeyboardSettings.dll',
    'Qt6VirtualKeyboardStyling.dll',
)


def _exclude_unused_binaries(binaries):
    filtered = []
    for entry in binaries:
        dest = entry[0].replace('\\', '/')
        if any(dest == b or dest.endswith('/' + b)
               for b in qt_unused_binaries):
            continue
        filtered.append(entry)
    return filtered


a = Analysis(
    ['gui_main.py'],
    pathex=[],
    binaries=[],
    datas=[
        # ExifTool configuration must land at <_MEIPASS>/configs/ExifTool_config
        # so that elodie.constants.exiftool_config resolves in frozen mode.
        ('configs/ExifTool_config', 'configs'),
        # The Chinese place-name database bundled with Elodie. cn_locations.py
        # resolves it at <_MEIPASS>/elodie/geolocations/zh_cn.pm.
        ('elodie/geolocations', 'elodie/geolocations'),
    ],
    hiddenimports=[
        # elodie media subclasses are resolved dynamically via get_all_subclasses()
        'elodie.media.media',
        'elodie.media.photo',
        'elodie.media.video',
        'elodie.media.audio',
        'elodie.media.text',
        'elodie.plugins.plugins',
    ],
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[
        # Qt modules this pure-Widgets app does not use
        'PySide6.QtQml',
        'PySide6.QtQuick',
        'PySide6.QtQuickWidgets',
        'PySide6.QtPdf',
        'PySide6.QtPdfWidgets',
        'PySide6.Qt3DCore',
        'PySide6.Qt3DRender',
        'PySide6.Qt3DExtras',
        'PySide6.Qt3DInput',
        'PySide6.Qt3DLogic',
        'PySide6.QtCharts',
        'PySide6.QtDataVisualization',
        'PySide6.QtMultimedia',
        'PySide6.QtMultimediaWidgets',
        'PySide6.QtOpenGL',
        'PySide6.QtSql',
        'PySide6.QtTest',
        'PySide6.QtWebEngineCore',
        'PySide6.QtWebEngineWidgets',
        'PySide6.QtWebChannel',
        'PySide6.QtPositioning',
        'PySide6.QtLocation',
        'PySide6.QtRemoteObjects',
        'PySide6.QtSensors',
        'PySide6.QtSerialPort',
        'PySide6.QtStateMachine',
        'PySide6.QtTextToSpeech',
        'PySide6.QtWebSockets',
        # NumPy is not required by the GUI at runtime (HEIC preview uses
        # pillow_heif which has no NumPy dependency).
        'numpy',
    ],
    win_no_prefer_redirects=False,
    win_private_assemblies=False,
    cipher=block_cipher,
    noarchive=False,
)

# Remove unused Qt binary modules from the collected binaries list.
a.binaries = _exclude_unused_binaries(a.binaries)

pyz = PYZ(a.pure, a.zipped_data, cipher=block_cipher)

exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name='Elodie GUI',
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    console=False,          # GUI app: no console window
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
)

coll = COLLECT(
    exe,
    a.binaries,
    a.zipfiles,
    a.datas,
    strip=False,
    upx=True,
    upx_exclude=[],
    name='Elodie GUI',
)
