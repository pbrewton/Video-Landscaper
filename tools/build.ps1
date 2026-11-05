[CmdletBinding()]
param(
    [switch]$Installer,
    [string]$MakeNsis
)

$ErrorActionPreference = 'Stop'
$ProjectRoot = Split-Path -Parent $PSScriptRoot
$Python = Join-Path $ProjectRoot '.venv\Scripts\python.exe'
$Spec = Join-Path $PSScriptRoot 'VideoLandscaper.spec'

if (-not (Test-Path -LiteralPath $Python -PathType Leaf)) {
    throw 'The build environment is missing. Follow docs/building.md to create .venv and install the build dependencies.'
}

if ($Installer) {
    if ($MakeNsis) {
        if (-not (Test-Path -LiteralPath $MakeNsis -PathType Leaf)) {
            throw "NSIS compiler not found: $MakeNsis"
        }
        $MakeNsis = (Resolve-Path -LiteralPath $MakeNsis).Path
    }
    else {
        $NsisCommand = Get-Command 'makensis.exe' -ErrorAction SilentlyContinue
        if ($NsisCommand) {
            $MakeNsis = $NsisCommand.Source
        }
        elseif (${env:ProgramFiles(x86)}) {
            $MakeNsis = Join-Path ${env:ProgramFiles(x86)} 'NSIS\makensis.exe'
        }
        if (-not $MakeNsis -or -not (Test-Path -LiteralPath $MakeNsis -PathType Leaf)) {
            throw 'NSIS is missing. Install NSIS or supply -MakeNsis with the full path to makensis.exe.'
        }
    }
}

Push-Location -LiteralPath $ProjectRoot
try {
    & $Python -m PyInstaller --noconfirm --clean `
        --distpath (Join-Path $ProjectRoot 'dist') `
        --workpath (Join-Path $ProjectRoot 'build') `
        $Spec
    if ($LASTEXITCODE -ne 0) {
        throw "PyInstaller failed with exit code $LASTEXITCODE."
    }

    if ($Installer) {
        & $MakeNsis (Join-Path $ProjectRoot 'installer\VideoLandscaper.nsi')
        if ($LASTEXITCODE -ne 0) {
            throw "NSIS failed with exit code $LASTEXITCODE."
        }
        Write-Host "Installer: $(Join-Path $ProjectRoot 'dist\VideoLandscaper-Setup.exe')"
    }
    Write-Host "App: $(Join-Path $ProjectRoot 'dist\VideoLandscaper\VideoLandscaper.exe')"
}
finally {
    Pop-Location
}
