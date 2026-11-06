$ErrorActionPreference = 'Stop'
# PowerShell otherwise reports only the last native exit code, hiding a failed archive operation.
$PSNativeCommandUseErrorActionPreference = $true

$verify = "$PSScriptRoot/../template/.github/actions/setup-windows/verify.ps1"
& $verify

# Match actions/cache's preferred Windows GNU tar, including support for TAR_OPTIONS.
$tar = "$env:ProgramFiles/Git/usr/bin/tar.exe"
$archive = "$env:RUNNER_TEMP/target-roundtrip.tar" -replace '\\', '/'
$marker = "$env:GITHUB_WORKSPACE/target/storage-marker.txt"
Set-Content -Path $marker -Value 'junction contents'
# Git's tar mishandles backslashes in -C during extraction; match actions/cache's working-directory approach.
Push-Location $env:GITHUB_WORKSPACE
try {
    & $tar --force-local -cf $archive target
    Remove-Item $marker
    & $tar --force-local -xf $archive
} finally {
    Pop-Location
}
& $verify
if ((Get-Content $marker) -ne 'junction contents') {
    throw 'The archive did not restore the target contents through the junction.'
}

# Existing caches predate the junction: ordinary directory entries must also restore safely.
$oldCache = New-Item -ItemType Directory -Path "$env:RUNNER_TEMP/old-cache/target" -Force
Set-Content -Path "$($oldCache.FullName)/old-cache-marker.txt" -Value 'ordinary directory'
Push-Location $oldCache.Parent.FullName
try {
    & $tar --force-local -cf $archive target
} finally {
    Pop-Location
}
Push-Location $env:GITHUB_WORKSPACE
try {
    & $tar --force-local -xf $archive
} finally {
    Pop-Location
}
& $verify
if ((Get-Content "$env:DEV_DRIVE/target/old-cache-marker.txt") -ne 'ordinary directory') {
    throw 'An ordinary target archive did not restore onto the Dev Drive.'
}

# Release staging must still find and run binaries through the unchanged target path.
$hostTriple = (rustc -vV | Select-String '^host: ').ToString().Substring(6)
cargo build --release --target $hostTriple
Copy-Item "target/$hostTriple/release/windows-storage-smoke.exe" "$env:RUNNER_TEMP/staged.exe"
& "$env:RUNNER_TEMP/staged.exe"
