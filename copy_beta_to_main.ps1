$sourceDir = "CommaxWallpadAddon_beta"
$destDir = "CommaxWallpadAddon"

Write-Host "베타 폴더의 파일들을 메인 폴더로 복사하는 중..."

# 모든 파일을 재귀적으로 가져와서 config.json과 CHANGELOG.md를 제외하고 복사
Get-ChildItem -Path $sourceDir -Recurse -File | 
    Where-Object { ($_.FullName -notlike "*config.json") -and ($_.Name -ne "CHANGELOG.md") } | 
    ForEach-Object {
        $destPath = $_.FullName.Replace($sourceDir, $destDir)
        $destFolder = Split-Path -Path $destPath -Parent

        # 대상 폴더가 없으면 생성
        if (!(Test-Path -Path $destFolder)) {
            New-Item -ItemType Directory -Path $destFolder -Force | Out-Null
        }

        # 파일 복사
        Copy-Item -Path $_.FullName -Destination $destPath -Force
        Write-Host "복사됨: $($_.FullName)"
    }

Write-Host "복사가 완료되었습니다." 