<#
.SYNOPSIS
    MaaWoA 启动脚本（PowerShell / Windows）。

.DESCRIPTION
    依赖缺失时自动调用 launch/setup.ps1 补齐，然后从项目根目录启动 GUI。

.EXAMPLE
    ./launch/launch.ps1
    缺依赖则自动安装，然后启动

.EXAMPLE
    ./launch/launch.ps1 -NoSetup
    不自动安装，缺依赖直接报错退出

.EXAMPLE
    ./launch/launch.ps1 -- --foo bar
    透传参数给 GUI
#>
[CmdletBinding()]
param(
    [switch]$NoSetup,
    [Parameter(ValueFromRemainingArguments)][string[]]$Rest
)

. "$PSScriptRoot/lib.ps1"

Set-Location -LiteralPath $env:MAAWOA_PROJECT_ROOT

# ---------------------------------------------------------------------------
# 解析 GUI 可执行文件
# ---------------------------------------------------------------------------

function Resolve-MaaWoALauncher {
    $candidates = if ($IsWindows) {
        @('MFAAvalonia.exe', 'mxu.exe', 'MFAAvalonia', 'mxu')
    }
    else {
        @('MFAAvalonia', 'mxu', 'MFAAvalonia.exe', 'mxu.exe')
    }

    foreach ($name in $candidates) {
        $path = Join-Path $env:MAAWOA_PROJECT_ROOT $name
        if (Test-Path -LiteralPath $path) { return $path }
    }
    return $null
}

# ---------------------------------------------------------------------------
# 主流程
# ---------------------------------------------------------------------------

Add-MaaWoAPathEntries

if ((-not (Test-MaaWoALauncher)) -or (-not (Test-MaaWoARuntime))) {
    if ($NoSetup) {
        Write-MaaWoAError '依赖不完整，且已指定 -NoSetup'
        Write-Host ''
        Write-MaaWoAStatus
        exit 1
    }
    Write-MaaWoAWarn '依赖不完整，先自动安装'
    & "$PSScriptRoot/setup.ps1" -Yes
    if ($LASTEXITCODE -ne 0) {
        Write-MaaWoAError '依赖安装失败，无法启动'
        exit 1
    }

    # 安装脚本刷新过 PATH，这里重新加载一次
    Add-MaaWoAPathEntries
}

$launcher = Resolve-MaaWoALauncher
if (-not $launcher) {
    Write-MaaWoAError '未在项目根目录找到 GUI 启动器（MFAAvalonia / mxu）'
    Write-MaaWoAInfo '可执行 launch/setup.ps1 重新部署'
    exit 1
}

# 防御性再确认可执行位与隔离属性（例如从压缩包解压出来的场景）
Reset-MaaWoALauncherPermissions

if (-not (Test-MaaWoADotnetMajor 10)) {
    Write-MaaWoAError '未找到 .NET 10 运行时'
    Write-MaaWoAInfo '可执行 launch/setup.ps1 自动安装'
    exit 1
}

Write-MaaWoAStep "启动 $(Split-Path -Leaf $launcher)"
Write-MaaWoADim "项目目录：$env:MAAWOA_PROJECT_ROOT"

# PowerShell 陷阱：`$x = if (...) { @() }` 会把空数组展开成 $null，
# 之后 @x 展开传参就会多出一个 $null 位置参数。必须显式初始化为空数组。
$arguments = @()
if ($Rest) { $arguments = @($Rest) }

& $launcher @arguments
exit $LASTEXITCODE
