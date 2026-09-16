<#
.SYNOPSIS
    MaaWoA 启动脚本公共库（PowerShell）。

.DESCRIPTION
    只应被 dot-source，不要直接执行：

        . "$PSScriptRoot/lib.ps1"

    所有函数以 MaaWoA 前缀命名，避免污染调用方命名空间。
#>

Set-StrictMode -Version Latest
$ErrorActionPreference = 'Stop'

# $IsWindows / $IsMacOS / $IsLinux 属于 PowerShell Core（pwsh）内置变量。
# Windows PowerShell 5.1 里不存在，且 StrictMode 下直接引用会报错，
# 因此这里统一补齐，让脚本在 5.1 与 7+ 上行为一致。
if ($PSVersionTable.PSVersion.Major -lt 6) {
    if (-not (Get-Variable -Name IsWindows -Scope Global -ErrorAction SilentlyContinue)) {
        $global:IsWindows = $true
        $global:IsMacOS = $false
        $global:IsLinux = $false
    }
}

# ---------------------------------------------------------------------------
# 项目根目录
# ---------------------------------------------------------------------------

# 本文件位于 <root>/launch/lib.ps1，因此根目录就是它的上一级。
# 可用 MAAWOA_PROJECT_ROOT 环境变量覆盖（打包出的壳程序依赖这个能力）。
if (-not $env:MAAWOA_PROJECT_ROOT) {
    $MaaWoA_LaunchDir = Split-Path -Parent $PSCommandPath
    $env:MAAWOA_PROJECT_ROOT = Split-Path -Parent $MaaWoA_LaunchDir
}
$env:MAAWOA_PROJECT_ROOT = (Resolve-Path -LiteralPath $env:MAAWOA_PROJECT_ROOT).Path

# ---------------------------------------------------------------------------
# 日志
# ---------------------------------------------------------------------------

function Write-MaaWoAInfo { param([Parameter(ValueFromRemainingArguments)][string[]]$Message) Write-Host "· $($Message -join ' ')" -ForegroundColor Cyan }
function Write-MaaWoAOk { param([Parameter(ValueFromRemainingArguments)][string[]]$Message) Write-Host "✓ $($Message -join ' ')" -ForegroundColor Green }
function Write-MaaWoAWarn { param([Parameter(ValueFromRemainingArguments)][string[]]$Message) Write-Host "! $($Message -join ' ')" -ForegroundColor Yellow }
function Write-MaaWoAError { param([Parameter(ValueFromRemainingArguments)][string[]]$Message) Write-Host "✗ $($Message -join ' ')" -ForegroundColor Red }
function Write-MaaWoADim { param([Parameter(ValueFromRemainingArguments)][string[]]$Message) Write-Host "$($Message -join ' ')" -ForegroundColor DarkGray }

$script:MaaWoAStepIndex = 0
$script:MaaWoAStepTotal = 0

function Write-MaaWoAStep {
    param([Parameter(ValueFromRemainingArguments)][string[]]$Message)
    $script:MaaWoAStepIndex++
    $prefix = if ($script:MaaWoAStepTotal -gt 0) { "[$($script:MaaWoAStepIndex)/$($script:MaaWoAStepTotal)] " } else { '' }
    Write-Host ''
    Write-Host "$prefix$($Message -join ' ')" -ForegroundColor White
}

# ---------------------------------------------------------------------------
# 基础探测
# ---------------------------------------------------------------------------

function Test-MaaWoACommand {
    param([Parameter(Mandatory)][string]$Name)
    return [bool](Get-Command $Name -ErrorAction SilentlyContinue)
}

# 输出 create-maa-project 使用的平台标识，例如 win-x64 / osx-arm64。
function Get-MaaWoARuntimePlatform {
    $os = if ($IsWindows) { 'win' }
    elseif ($IsMacOS) { 'osx' }
    elseif ($IsLinux) { 'linux' }
    else {
        Write-MaaWoAError "不支持的操作系统：$([System.Environment]::OSVersion.Platform)"
        throw 'unsupported OS'
    }

    $archName = [System.Runtime.InteropServices.RuntimeInformation]::OSArchitecture.ToString()
    $arch = switch ($archName) {
        'Arm64' { 'arm64' }
        'X64' { 'x64' }
        'X86' { 'x64' }
        default {
            Write-MaaWoAError "不支持的 CPU 架构：$archName"
            throw 'unsupported architecture'
        }
    }

    return "$os-$arch"
}

# .NET 运行时安装位置。MFAAvalonia 是 net10.0 框架依赖程序。
function Get-MaaWoADotnetRoot {
    if ($env:DOTNET_ROOT -and (Test-Path -LiteralPath (Join-Path $env:DOTNET_ROOT 'dotnet.exe'))) {
        return $env:DOTNET_ROOT
    }
    if ($env:DOTNET_ROOT -and (Test-Path -LiteralPath (Join-Path $env:DOTNET_ROOT 'dotnet'))) {
        return $env:DOTNET_ROOT
    }

    $userDotnet = Join-Path $HOME '.dotnet'
    if ((Test-Path -LiteralPath (Join-Path $userDotnet 'dotnet.exe')) -or
        (Test-Path -LiteralPath (Join-Path $userDotnet 'dotnet'))) {
        return $userDotnet
    }

    if (Test-MaaWoACommand 'dotnet') {
        return (Split-Path -Parent (Get-Command dotnet).Source)
    }

    return $null
}

# 检查 .NET 主版本是否满足要求（默认 10）。
function Test-MaaWoADotnetMajor {
    param([int]$Required = 10)

    $root = Get-MaaWoADotnetRoot
    if (-not $root) { return $false }

    $exe = Join-Path $root $(if ($IsWindows) { 'dotnet.exe' } else { 'dotnet' })
    if (-not (Test-Path -LiteralPath $exe)) { return $false }

    $major = & $exe --list-runtimes 2>$null |
        ForEach-Object { if ($_ -match '^Microsoft\.NETCore\.App\s+(\d+)\.') { [int]$Matches[1] } } |
        Sort-Object -Descending |
        Select-Object -First 1

    return ($null -ne $major -and $major -ge $Required)
}

# ---------------------------------------------------------------------------
# 依赖状态
# ---------------------------------------------------------------------------

function Get-MaaWoARuntimeDir { Join-Path $env:MAAWOA_PROJECT_ROOT '.create-maa-project/runtime' }
function Get-MaaWoAMfaaDir { Join-Path (Get-MaaWoARuntimeDir) "mfaa/$(Get-MaaWoARuntimePlatform)" }
function Get-MaaWoAPythonDir { Join-Path (Get-MaaWoARuntimeDir) "python/$(Get-MaaWoARuntimePlatform)" }

function Test-MaaWoANode {
    if (-not (Test-MaaWoACommand 'node')) { return $false }
    $version = (& node -v 2>$null) -replace '^v', ''
    $parts = $version -split '\.'
    if ($parts.Count -lt 2) { return $false }
    $major = [int]$parts[0]
    $minor = [int]$parts[1]
    return ($major -gt 22 -or ($major -eq 22 -and $minor -ge 13))
}

function Test-MaaWoAPnpm { Test-MaaWoACommand 'pnpm' }
function Test-MaaWoAUv { Test-MaaWoACommand 'uv' }

function Test-MaaWoASubmodule {
    Test-Path -LiteralPath (Join-Path $env:MAAWOA_PROJECT_ROOT 'MaaCommonAssets/OCR/ppocr_v6/small/det.onnx')
}

function Test-MaaWoANodeDeps {
    Test-Path -LiteralPath (Join-Path $env:MAAWOA_PROJECT_ROOT 'node_modules/@nekosu/maa-tools')
}

function Test-MaaWoAPythonDeps {
    $venv = Join-Path $env:MAAWOA_PROJECT_ROOT '.venv'
    (Test-Path -LiteralPath (Join-Path $venv 'Scripts/python.exe')) -or
    (Test-Path -LiteralPath (Join-Path $venv 'bin/python3'))
}

function Test-MaaWoARuntime {
    $platform = Get-MaaWoARuntimePlatform
    $native = Join-Path $env:MAAWOA_PROJECT_ROOT "runtimes/$platform/native"
    (Test-Path -LiteralPath (Join-Path $native 'MaaFramework.dll')) -or
    (Test-Path -LiteralPath (Join-Path $native 'libMaaFramework.dylib')) -or
    (Test-Path -LiteralPath (Join-Path $native 'libMaaFramework.so'))
}

function Test-MaaWoAOcr {
    $dir = Join-Path $env:MAAWOA_PROJECT_ROOT 'resource/base/model/ocr'
    (Test-Path -LiteralPath (Join-Path $dir 'det.onnx')) -and
    (Test-Path -LiteralPath (Join-Path $dir 'rec.onnx')) -and
    (Test-Path -LiteralPath (Join-Path $dir 'keys.txt'))
}

function Test-MaaWoALauncher {
    foreach ($name in @('MFAAvalonia.exe', 'MFAAvalonia', 'mxu.exe', 'mxu')) {
        if (Test-Path -LiteralPath (Join-Path $env:MAAWOA_PROJECT_ROOT $name)) { return $true }
    }
    return $false
}

# 打印依赖状态表。返回 $true 表示全部就绪。
function Write-MaaWoAStatus {
    $allOk = $true

    if (Test-MaaWoANode) { Write-MaaWoAOk "Node.js $(& node -v)" } else { Write-MaaWoAWarn 'Node.js 缺失或版本过低（需要 >= 22.13）'; $allOk = $false }
    if (Test-MaaWoAPnpm) { Write-MaaWoAOk "pnpm $(& pnpm -v 2>$null)" } else { Write-MaaWoAWarn 'pnpm 缺失（可通过 corepack 自动提供）'; $allOk = $false }
    if (Test-MaaWoAUv) { Write-MaaWoAOk "uv $((& uv --version 2>$null) -split ' ' | Select-Object -Index 1)" } else { Write-MaaWoAWarn 'uv 缺失'; $allOk = $false }
    if (Test-MaaWoASubmodule) { Write-MaaWoAOk 'MaaCommonAssets 子模块' } else { Write-MaaWoAWarn 'MaaCommonAssets 子模块未初始化'; $allOk = $false }
    if (Test-MaaWoANodeDeps) { Write-MaaWoAOk 'Node 依赖' } else { Write-MaaWoAWarn 'Node 依赖未安装（pnpm install）'; $allOk = $false }
    if (Test-MaaWoAPythonDeps) { Write-MaaWoAOk 'Python 依赖' } else { Write-MaaWoAWarn 'Python 依赖未安装（uv sync）'; $allOk = $false }
    if (Test-MaaWoARuntime) { Write-MaaWoAOk 'MaaFramework 运行时' } else { Write-MaaWoAWarn 'MaaFramework 运行时未同步（pnpm sync:runtime）'; $allOk = $false }
    if (Test-MaaWoAOcr) { Write-MaaWoAOk 'OCR 模型' } else { Write-MaaWoAWarn 'OCR 模型缺失'; $allOk = $false }
    if (Test-MaaWoALauncher) { Write-MaaWoAOk 'GUI 启动器' } else { Write-MaaWoAWarn 'GUI 启动器未就位'; $allOk = $false }
    if (Test-MaaWoADotnetMajor 10) { Write-MaaWoAOk '.NET 10 运行时' } else { Write-MaaWoAWarn '.NET 10 运行时缺失'; $allOk = $false }

    return $allOk
}

# 把 GUI 发行内容铺到项目根目录。
#
# 通用 GUI 从「自身可执行文件所在目录」读取 interface.json，因此必须与项目根目录
# 的 interface.json / resource / runtimes 同级。已存在的文件不覆盖，保证
# sync:runtime 生成的 runtimes/libs/plugins 不被破坏。
function Invoke-MaaWoADeployLauncher {
    param(
        [Parameter(Mandatory)][string]$SourceDir
    )

    if (-not (Test-Path -LiteralPath $SourceDir)) {
        Write-MaaWoAError "未找到 GUI 发行目录：$SourceDir"
        return $false
    }

    $destination = $env:MAAWOA_PROJECT_ROOT

    # 优先用 robocopy：/XC /XN /XO 跳过已存在文件，避免覆盖运行时
    if (Test-MaaWoACommand 'robocopy') {
        $result = & robocopy $SourceDir $destination /E /XC /XN /XO /NFL /NDL /NJH /NJS /NP
        # robocopy 退出码 0-7 均为成功
        $code = $LASTEXITCODE
        if ($code -ge 8) {
            Write-MaaWoAError "robocopy 失败（退出码 $code）"
            return $false
        }
    }
    else {
        Get-ChildItem -LiteralPath $SourceDir -Recurse -Force | ForEach-Object {
            $relative = $_.FullName.Substring($SourceDir.Length).TrimStart('\', '/')
            $target = Join-Path $destination $relative
            if ($_.PSIsContainer) {
                if (-not (Test-Path -LiteralPath $target)) {
                    New-Item -ItemType Directory -Path $target -Force | Out-Null
                }
            }
            elseif (-not (Test-Path -LiteralPath $target)) {
                $parent = Split-Path -Parent $target
                if (-not (Test-Path -LiteralPath $parent)) {
                    New-Item -ItemType Directory -Path $parent -Force | Out-Null
                }
                Copy-Item -LiteralPath $_.FullName -Destination $target
            }
        }
    }

    Reset-MaaWoALauncherPermissions
    return $true
}

# 清除 macOS 隔离属性并补齐可执行位。
function Reset-MaaWoALauncherPermissions {
    foreach ($name in @('MFAAvalonia', 'mxu')) {
        $target = Join-Path $env:MAAWOA_PROJECT_ROOT $name
        if (-not (Test-Path -LiteralPath $target)) { continue }

        if (-not $IsWindows) {
            & chmod +x $target 2>$null
        }
        if ($IsMacOS -and (Test-MaaWoACommand 'xattr')) {
            & xattr -dr com.apple.quarantine $target 2>$null
            & xattr -dr com.apple.provenance $target 2>$null
        }
    }

    if ($IsMacOS -and (Test-MaaWoACommand 'xattr')) {
        $libloader = Join-Path $env:MAAWOA_PROJECT_ROOT 'libloader.dll'
        if (Test-Path -LiteralPath $libloader) {
            & xattr -dr com.apple.quarantine $libloader 2>$null
        }
    }
}

# 图形界面启动时 PATH 往往很精简，显式补齐常用位置。
function Add-MaaWoAPathEntries {
    $candidates = @(
        (Join-Path $HOME '.local/bin')
        (Join-Path $HOME '.dotnet')
        '/opt/homebrew/bin'
        '/usr/local/bin'
    )

    foreach ($dir in $candidates) {
        if (-not (Test-Path -LiteralPath $dir)) { continue }
        $current = $env:PATH -split [IO.Path]::PathSeparator
        if ($current -notcontains $dir) {
            $env:PATH = $dir + [IO.Path]::PathSeparator + $env:PATH
        }
    }

    $dotnetRoot = Get-MaaWoADotnetRoot
    if ($dotnetRoot) { $env:DOTNET_ROOT = $dotnetRoot }
}
