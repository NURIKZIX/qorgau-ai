param([switch]$OneFile)
$ErrorActionPreference = 'Stop'
$projectRoot = Split-Path -Parent $PSScriptRoot
Set-Location -LiteralPath $projectRoot
$env:MPLBACKEND = 'Agg'
$env:MPLCONFIGDIR = Join-Path $projectRoot '.cache\matplotlib-build'
New-Item -ItemType Directory -Path $env:MPLCONFIGDIR -Force | Out-Null
$pythonPath = Join-Path $projectRoot '.venv\Scripts\python.exe'
if (-not (Test-Path -LiteralPath $pythonPath)) { throw 'Create .venv and install requirements-build.txt first. See README.md.' }
foreach ($modelName in @('yolo11n.onnx','face_landmarker.task','manifest.json')) {
    if (-not (Test-Path -LiteralPath (Join-Path $projectRoot "models\$modelName"))) { throw "Missing model asset: $modelName" }
}
$manifest = Get-Content -LiteralPath (Join-Path $projectRoot 'models\manifest.json') -Raw | ConvertFrom-Json
foreach ($assetName in @('yolo11n.onnx','face_landmarker.task')) {
    $assetHash = (Get-FileHash -Algorithm SHA256 -LiteralPath (Join-Path $projectRoot "models\$assetName")).Hash.ToLowerInvariant()
    if ($assetHash -ne $manifest.models.$assetName.sha256) { throw "Model checksum mismatch: $assetName" }
}
$argsList = @('-m','PyInstaller','--noconfirm','--clean','--windowed','--name','QORGAU AI',
    '--runtime-hook','scripts\preload_dateutil.py',
    '--add-data','models\yolo11n.onnx;models','--add-data','models\face_landmarker.task;models',
    '--add-data','models\manifest.json;models','--add-data','README.md;.',
    '--add-data','THIRD_PARTY_NOTICES.md;.', '--add-data','LICENSE;.',
    '--collect-data','mediapipe', '--collect-binaries','mediapipe',
    '--collect-data','onnxruntime', '--collect-binaries','onnxruntime',
    '--exclude-module','torch','--exclude-module','torchvision','--exclude-module','ultralytics',
    '--exclude-module','IPython','--exclude-module','tkinter','--exclude-module','jax', '--exclude-module','jaxlib',
    '--exclude-module','scipy','--exclude-module','tensorflow','--exclude-module','PySide6.QtQml',
    '--exclude-module','PySide6.QtQuick','--exclude-module','PySide6.QtNetwork',
    '--exclude-module','PySide6.QtOpenGL','--exclude-module','PySide6.QtOpenGLWidgets')
# Use the project's runtime and Windows libraries. Third-party DLL directories
# on the caller's PATH must not contaminate the portable application.
$qtBinaryDirectory = Join-Path $projectRoot '.venv\Lib\site-packages\PySide6'
$pythonBaseDirectory = & $pythonPath -c 'import sys; print(sys.base_prefix)'
$originalBuildPath = $env:PATH
$env:PATH = @($qtBinaryDirectory, (Split-Path -Parent $pythonPath), $pythonBaseDirectory,
    (Join-Path $env:WINDIR 'System32'), $env:WINDIR) -join ';'
foreach ($runtimeDllName in @('msvcp140.dll','msvcp140_1.dll','msvcp140_2.dll','msvcp140_codecvt_ids.dll','vcruntime140.dll','vcruntime140_1.dll','concrt140.dll')) {
    $runtimeDllPath = Join-Path $qtBinaryDirectory $runtimeDllName
    if (-not (Test-Path -LiteralPath $runtimeDllPath)) { throw "Missing Qt C++ runtime: $runtimeDllName" }
    $argsList += @('--add-binary', "$runtimeDllPath;.")
}
if ($OneFile) { $argsList += '--onefile' } else { $argsList += '--onedir' }
$argsList += 'main.py'
try {
    & $pythonPath @argsList
    if ($LASTEXITCODE -ne 0) { throw 'PyInstaller build failed' }
} finally {
    $env:PATH = $originalBuildPath
}
Write-Output 'Build complete. Keep the entire dist\QORGAU AI directory when using the default portable build.'
