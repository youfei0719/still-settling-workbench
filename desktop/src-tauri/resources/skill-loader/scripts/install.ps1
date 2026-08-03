$ErrorActionPreference = "Stop"
param(
  [string]$RepositoryUrl = $env:DOUYIN_WRITING_SKILLS_REPO_URL,
  [string]$TargetDir = $env:DOUYIN_WRITING_SKILLS_TARGET_DIR
)

$SourceDir = Split-Path -Parent (Split-Path -Parent $PSCommandPath)
if ([string]::IsNullOrWhiteSpace($RepositoryUrl) -and (git -C $SourceDir rev-parse --is-inside-work-tree 2>$null) -eq "true") {
  $RepositoryUrl = git -C $SourceDir remote get-url origin
}
if ([string]::IsNullOrWhiteSpace($RepositoryUrl)) {
  throw "请传入目标 Skill 仓库地址，或设置 DOUYIN_WRITING_SKILLS_REPO_URL。"
}
if ([string]::IsNullOrWhiteSpace($TargetDir)) {
  $RepositoryName = [System.IO.Path]::GetFileNameWithoutExtension($RepositoryUrl.TrimEnd('/'))
  $TargetDir = Join-Path $HOME ".agents\skills\$RepositoryName"
}

if (-not (Get-Command git -ErrorAction SilentlyContinue)) {
  throw "需要先安装 Git。"
}
New-Item -ItemType Directory -Force -Path (Split-Path $TargetDir) | Out-Null

if (-not (Test-Path $TargetDir)) {
  git clone $RepoUrl $TargetDir
} else {
  $isRepo = git -C $TargetDir rev-parse --is-inside-work-tree 2>$null
  $origin = git -C $TargetDir remote get-url origin 2>$null
  if ($isRepo -ne "true" -or $origin -ne $RepositoryUrl) {
    throw "目标目录已存在，但 remote 与目标 Skill 仓库不一致：$TargetDir"
  }
  $branch = git -C $TargetDir branch --show-current
  git -C $TargetDir pull --ff-only origin $branch
}

if (Get-Command python3 -ErrorAction SilentlyContinue) {
  python3 "$TargetDir/scripts/load_latest.py"
} else {
  python "$TargetDir/scripts/load_latest.py"
}
Write-Host "安装完成。在 Codex 中直接使用：请用 douyin-writing-skills 写一条抖音口播。"
