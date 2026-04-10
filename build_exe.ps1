#!/usr/bin/env pwsh
<#
.SYNOPSIS
Build the HiddenLodge Desktop Bridge as a standalone Windows executable using PyInstaller.
#>

$ErrorActionPreference = "Stop"

$ScriptDir  = Split-Path -Parent $MyInvocation.MyCommand.Path
$PythonExe  = Join-Path $ScriptDir ".venv\Scripts\python.exe"
$MainScript = Join-Path $ScriptDir "main.py"
$OutputDir  = Join-Path $ScriptDir "dist"
$BuildDir   = Join-Path $ScriptDir "build"

if (-not (Test-Path $PythonExe)) {
    Write-Error "Python executable not found at: $PythonExe. Run: python -m venv .venv"
    exit 1
}

Write-Host "Building HiddenLodge Desktop Bridge..." -ForegroundColor Cyan

& $PythonExe -m PyInstaller `
    --onefile `
    --windowed `
    --name "HiddenLodgeDesktop" `
    --add-data "config.example.json;." `
    --add-data "version.txt;." `
    --distpath $OutputDir `
    --workpath $BuildDir `
    --specpath $ScriptDir `
    $MainScript

if ($LASTEXITCODE -ne 0) {
    Write-Error "PyInstaller build failed."
    exit $LASTEXITCODE
}

Write-Host "Build complete: $OutputDir\HiddenLodgeDesktop.exe" -ForegroundColor Green
