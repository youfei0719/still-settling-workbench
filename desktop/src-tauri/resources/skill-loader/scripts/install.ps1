$ErrorActionPreference = "Stop"
$RepoUrl = "https://github.com/youfei0719/douyin-writing-skills.git"
$TargetDir = Join-Path $HOME ".agents\skills\douyin-writing-skills"

if (-not (Get-Command git -ErrorAction SilentlyContinue)) {
  throw "需要先安装 Git。"
}
New-Item -ItemType Directory -Force -Path (Split-Path $TargetDir) | Out-Null

if (-not (Test-Path $TargetDir)) {
  git clone $RepoUrl $TargetDir
} else {
  $isRepo = git -C $TargetDir rev-parse --is-inside-work-tree 2>$null
  $origin = git -C $TargetDir remote get-url origin 2>$null
  if ($isRepo -ne "true" -or $origin -notmatch "github\.com[:/]youfei0719/douyin-writing-skills(\.git)?$") {
    throw "目标目录已存在，但不是 douyin-writing-skills Git 仓库：$TargetDir"
  }
  git -C $TargetDir pull --ff-only origin main
}

if (Get-Command python3 -ErrorAction SilentlyContinue) {
  python3 "$TargetDir/scripts/load_latest.py"
} else {
  python "$TargetDir/scripts/load_latest.py"
}
Write-Host "安装完成。在 Codex 中直接使用：请用 douyin-writing-skills 写一条抖音口播。"
