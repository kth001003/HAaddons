# Encoding settings
$PSDefaultParameterValues['*:Encoding'] = 'utf8'
[Console]::OutputEncoding = [System.Text.Encoding]::UTF8
$OutputEncoding = [System.Text.Encoding]::UTF8

$sourceDir = "CommaxWallpadAddon_beta"
$destDir = "CommaxWallpadAddon"

Write-Host "Copying files from beta folder to main folder..."

# Copy all files recursively except config.json, CHANGELOG.md, and tests/docs folders
Get-ChildItem -Path $sourceDir -Recurse -File | 
    Where-Object { 
        ($_.Name -ne "config.json") -and 
        ($_.Name -ne "CHANGELOG.md") -and 
        ($_.FullName -notlike "*\tests\*") -and 
        ($_.FullName -notlike "*\docs\*")
    } | 
    ForEach-Object {
        $destPath = $_.FullName.Replace($sourceDir, $destDir)
        $destFolder = Split-Path -Path $destPath -Parent

        # Create destination folder if it doesn't exist
        if (!(Test-Path -Path $destFolder)) {
            New-Item -ItemType Directory -Path $destFolder -Force | Out-Null
        }

        # Copy file
        Copy-Item -Path $_.FullName -Destination $destPath -Force
        # Display relative path instead of full path
        $relativePath = $_.FullName.Substring($_.FullName.IndexOf($sourceDir))
        Write-Host "Copied: $relativePath"
    }

Write-Host "Copy completed." 