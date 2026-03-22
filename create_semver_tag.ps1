Param(
    [Parameter(Mandatory = $true)]
    [string]$Version,

    [string]$Message = ""
)

$ErrorActionPreference = "Stop"

if ($Version -notmatch '^[0-9]+\.[0-9]+\.[0-9]+(-[0-9A-Za-z.-]+)?$') {
    throw "Invalid version '$Version'. Use semver like 1.0.1, 1.1.0, or 2.0.0-rc.1"
}

$projectRoot = Split-Path -Parent $MyInvocation.MyCommand.Path
Set-Location $projectRoot

$insideRepo = git rev-parse --is-inside-work-tree 2>$null
if ($LASTEXITCODE -ne 0 -or $insideRepo.Trim() -ne "true") {
    throw "Current directory is not a git repository: $projectRoot"
}

$workingTreeChanges = git status --porcelain
if ($workingTreeChanges) {
    throw "Working tree is not clean. Commit or stash changes before creating a release tag."
}

$tag = "v$Version"
$tagMessage = if ([string]::IsNullOrWhiteSpace($Message)) { "Release $tag" } else { $Message }

Write-Host "[Tag] Fetching tags from origin"
git fetch --tags origin
if ($LASTEXITCODE -ne 0) {
    throw "Failed to fetch tags from origin"
}

$localTag = git tag --list $tag
if ($localTag) {
    throw "Tag $tag already exists locally"
}

$remoteTag = git ls-remote --tags --refs origin "refs/tags/$tag"
if ($remoteTag) {
    throw "Tag $tag already exists on origin"
}

Write-Host "[Tag] Creating annotated tag $tag"
git tag -a $tag -m $tagMessage
if ($LASTEXITCODE -ne 0) {
    throw "Failed to create tag $tag"
}

Write-Host "[Tag] Pushing $tag to origin"
git push origin $tag
if ($LASTEXITCODE -ne 0) {
    throw "Failed to push tag $tag"
}

Write-Host "[Tag] Success: $tag created and pushed"
Write-Host "[Tag] GitHub Actions will now publish a release for this tag."