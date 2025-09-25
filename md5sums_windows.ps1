# Usage: runs MD5 checksum verification on Windows PCs
param (
    [string]$ChecksumFile = "mpd.v1\md5sums"
)

Get-Content $ChecksumFile | ForEach-Object {
    $parts = $_ -split ' +'
    if ($parts.Length -lt 2) { return }

    $expectedHash = $parts[0].ToLower()
    $file = "mpd.v1\"+$parts[1]

    if (-Not (Test-Path $file)) {
        Write-Host "${file}: FILE NOT FOUND" -ForegroundColor Red
        return
    }

    $certOutput = CertUtil -hashfile $file MD5
    $actualHash = ($certOutput[1] -replace ' ', '').ToLower() # CertUtil output includes extra lines; the second line contains the hash

    if ($actualHash -eq $expectedHash) {
        Write-Host "${file}: OK" -ForegroundColor Green
    } else {
        Write-Host "${file}: FAILED" -ForegroundColor Red
    }
}
