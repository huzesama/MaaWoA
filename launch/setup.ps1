<#
.SYNOPSIS
    MaaWoA 依赖一键安装（PowerShell / Windows）。

.DESCRIPTION
    幂等：已就绪的步骤自动跳过，可反复执行。

.EXAMPLE
    ./launch/setup.ps1
    安装/补齐全部依赖

.EXAMPLE
    ./launch/setup.ps1 -Check
    只检查状态，不做任何改动

.EXAMPLE
    ./launch/setup.ps1 -Yes
    全部自动确认（非交互）
#>
[CmdletBinding()]
param(
    [switch]$Check,
    [switch]$Yes,
    [switch]$Force
)

. "$PSScriptRoot/lib.ps1"

# corepack 首次使用 packageManager 指定的 pnpm 版本时会询问是否下载，
# 关闭询问让安装过程完全非交互。
$env:COREPACK_ENABLE_DOWNLOAD_PROMPT = '0'

# 标题不占用步骤编号，7 个安装阶段 + 校验 = 8
$script:MaaWoAStepTotal = 8

Set-Location -LiteralPath $env:MAAWOA_PROJECT_ROOT

# ---------------------------------------------------------------------------
# 交互辅助
# ---------------------------------------------------------------------------

function Confirm-MaaWoAAction {
    param([Parameter(Mandatory)][string]$Prompt)

    if ($Yes) {
        Write-MaaWoAInfo "$Prompt（-Yes 自动确认）"
        return $true
    }

    $reply = Read-Host "$Prompt [y/N]"
    return ($reply -match '^[Yy]$')
}

# 包装子步骤，失败时给出可读上下文。
function Invoke-MaaWoAStep {
    param(
        [Parameter(Mandatory)][string]$Description,
        [Parameter(Mandatory)][scriptblock]$Action
    )

    try {
        # $LASTEXITCODE 是全局的，会残留上一条外部命令的退出码（例如 robocopy
        # 成功时返回 1）。先清零，避免把无关命令的退出码误判成本次失败。
        $global:LASTEXITCODE = 0
        $result = & $Action

        # 外部命令失败不会抛异常，需要显式检查退出码；
        # 纯 PowerShell 函数不设置 $LASTEXITCODE，改用返回值判断。
        if ($LASTEXITCODE -ne 0) {
            throw "退出码 $LASTEXITCODE"
        }
        if ($result -eq $false) {
            return $false
        }
        return $true
    }
    catch {
        Write-MaaWoAError "$Description 失败：$($_.Exception.Message)"
        return $false
    }
}

# ---------------------------------------------------------------------------
# 各依赖的安装动作
# ---------------------------------------------------------------------------

function Install-MaaWoANode {
    if (Test-MaaWoACommand 'winget') {
        if (-not (Confirm-MaaWoAAction '使用 winget 安装 Node.js 22？')) { return $false }
        & winget install --id OpenJS.NodeJS.LTS --accept-source-agreements --accept-package-agreements
        return $true
    }
    if (Test-MaaWoACommand 'choco') {
        if (-not (Confirm-MaaWoAAction '使用 Chocolatey 安装 Node.js 22？')) { return $false }
        & choco install nodejs-lts -y
        return $true
    }

    Write-MaaWoAError '未找到 winget 或 choco，无法自动安装 Node.js'
    Write-MaaWoAInfo '请手动安装 Node.js >= 22.13：https://nodejs.org/'
    return $false
}

function Install-MaaWoAPnpm {
    if (Test-MaaWoACommand 'corepack') {
        Write-MaaWoAInfo '通过 corepack 启用 pnpm ...'
        & corepack enable pnpm 2>$null
        if ($LASTEXITCODE -ne 0) { & corepack prepare --activate 2>$null }
    }

    if (-not (Test-MaaWoAPnpm)) {
        Write-MaaWoAError 'pnpm 不可用'
        Write-MaaWoAInfo '请手动安装：npm install -g pnpm'
        return $false
    }
    return $true
}

function Install-MaaWoAUv {
    if (-not (Confirm-MaaWoAAction '通过官方脚本安装 uv？')) { return $false }

    Write-MaaWoAInfo '下载并安装 uv ...'
    & powershell -ExecutionPolicy ByPass -c 'irm https://astral.sh/uv/install.ps1 | iex'
    if ($LASTEXITCODE -ne 0) { return $false }

    # 官方脚本装到 %USERPROFILE%\.local\bin，当前会话的 PATH 尚未刷新
    $uvBin = Join-Path $HOME '.local/bin'
    if (Test-Path -LiteralPath $uvBin) {
        $env:PATH = $uvBin + [IO.Path]::PathSeparator + $env:PATH
    }

    if (-not (Test-MaaWoAUv)) {
        Write-MaaWoAError 'uv 安装后仍不可用，请重开终端后再试'
        return $false
    }
    return $true
}

function Initialize-MaaWoASubmodule {
    & git submodule update --init --depth 1 MaaCommonAssets
}

function Install-MaaWoANodeDeps {
    & pnpm install
}

function Install-MaaWoAPythonDeps {
    # --frozen：只按 uv.lock 安装，避免被本地 PyPI 镜像配置改写锁文件
    & uv sync --frozen
}

function Sync-MaaWoARuntime {
    $env:CREATE_MAA_PROJECT_RUNTIME_PLATFORM = Get-MaaWoARuntimePlatform
    & pnpm sync:runtime
}

function Install-MaaWoADotnet {
    $installDir = Join-Path $HOME '.dotnet'
    $tmpScript = Join-Path ([IO.Path]::GetTempPath()) "dotnet-install-$([guid]::NewGuid().ToString('N')).ps1"

    Write-MaaWoAInfo '下载 dotnet-install.ps1 ...'
    Invoke-WebRequest -Uri 'https://dot.net/v1/dotnet-install.ps1' -OutFile $tmpScript -UseBasicParsing

    Write-MaaWoAInfo "安装 .NET 10 运行时到 $installDir ..."
    & powershell -ExecutionPolicy ByPass -File $tmpScript -Channel 10.0 -Runtime dotnet -InstallDir $installDir
    $code = $LASTEXITCODE
    Remove-Item -LiteralPath $tmpScript -ErrorAction SilentlyContinue

    if ($code -ne 0) { return $false }

    $env:DOTNET_ROOT = $installDir
    $env:PATH = "$installDir$([IO.Path]::PathSeparator)$env:PATH"
    return $true
}

function Install-MaaWoALauncher {
    Invoke-MaaWoADeployLauncher -SourceDir (Get-MaaWoAMfaaDir)
}

# ---------------------------------------------------------------------------
# 主流程
# ---------------------------------------------------------------------------

if ($Check) {
    Write-Host ''
    Write-Host 'MaaWoA 依赖状态' -ForegroundColor White
    Write-MaaWoADim "项目目录：$env:MAAWOA_PROJECT_ROOT"
    Write-MaaWoADim "平台标识：$(Get-MaaWoARuntimePlatform)"
    Write-Host ''
    if (Write-MaaWoAStatus) {
        Write-Host ''
        Write-MaaWoAOk '全部依赖已就绪'
        exit 0
    }
    Write-Host ''
    Write-MaaWoAWarn '存在缺失依赖，执行 launch/setup.ps1 补齐'
    exit 1
}

Write-Host ''
Write-Host 'MaaWoA 依赖安装' -ForegroundColor White
Write-MaaWoADim "项目目录：$env:MAAWOA_PROJECT_ROOT"
Write-MaaWoADim "平台标识：$(Get-MaaWoARuntimePlatform)"

# 1. 基础工具 --------------------------------------------------------------
Write-MaaWoAStep '检查基础工具'

if (-not (Test-MaaWoANode)) {
    if (Test-MaaWoACommand 'node') {
        Write-MaaWoAWarn "Node.js $(& node -v) 版本过低，需要 >= 22.13"
    }
    else {
        Write-MaaWoAWarn '未找到 Node.js'
    }
    if (-not (Invoke-MaaWoAStep 'Node.js 安装' { Install-MaaWoANode })) { exit 1 }
    # winget/choco 安装后当前会话 PATH 未刷新
    $nodeDir = Join-Path ${env:ProgramFiles} 'nodejs'
    if ((Test-Path -LiteralPath $nodeDir) -and ($env:PATH -notlike "*$nodeDir*")) {
        $env:PATH = $nodeDir + [IO.Path]::PathSeparator + $env:PATH
    }
}
Write-MaaWoAOk "Node.js $(& node -v)"

if (-not (Test-MaaWoAPnpm)) {
    Write-MaaWoAWarn '未找到 pnpm'
    if (-not (Invoke-MaaWoAStep 'pnpm 初始化' { Install-MaaWoAPnpm })) { exit 1 }
}
Write-MaaWoAOk "pnpm $(& pnpm -v)"

if (-not (Test-MaaWoAUv)) {
    Write-MaaWoAWarn '未找到 uv'
    if (-not (Invoke-MaaWoAStep 'uv 安装' { Install-MaaWoAUv })) { exit 1 }
}
Write-MaaWoAOk "uv $((& uv --version) -split ' ' | Select-Object -Index 1)"

# 2. 子模块 ----------------------------------------------------------------
Write-MaaWoAStep '初始化 MaaCommonAssets 子模块'
if ((-not $Force) -and (Test-MaaWoASubmodule)) {
    Write-MaaWoADim '已初始化，跳过'
}
elseif (-not (Invoke-MaaWoAStep '子模块初始化' { Initialize-MaaWoASubmodule })) {
    exit 1
}
Write-MaaWoAOk 'OCR 资源就位'

# 3. Node 依赖 -------------------------------------------------------------
Write-MaaWoAStep '安装 Node 依赖'
if ((-not $Force) -and (Test-MaaWoANodeDeps)) {
    Write-MaaWoADim '已安装，跳过'
}
elseif (-not (Invoke-MaaWoAStep 'pnpm install' { Install-MaaWoANodeDeps })) {
    exit 1
}
Write-MaaWoAOk 'Node 依赖就绪'

# 4. Python 依赖 -----------------------------------------------------------
Write-MaaWoAStep '安装 Python 依赖'
if ((-not $Force) -and (Test-MaaWoAPythonDeps)) {
    Write-MaaWoADim '已安装，跳过'
}
elseif (-not (Invoke-MaaWoAStep 'uv sync' { Install-MaaWoAPythonDeps })) {
    exit 1
}
Write-MaaWoAOk 'Python 依赖就绪'

# 5. 运行时资源 ------------------------------------------------------------
Write-MaaWoAStep '同步 MaaFramework / OCR / GUI 运行时'
Write-MaaWoADim '首次执行需要下载较多内容，请耐心等待'
if ((-not $Force) -and (Test-MaaWoARuntime) -and (Test-MaaWoAOcr)) {
    Write-MaaWoADim '已同步，跳过'
}
elseif (-not (Invoke-MaaWoAStep 'pnpm sync:runtime' { Sync-MaaWoARuntime })) {
    exit 1
}
Write-MaaWoAOk '运行时资源就绪'

# 6. .NET 运行时 -----------------------------------------------------------
Write-MaaWoAStep '检查 .NET 10 运行时'
if ((-not $Force) -and (Test-MaaWoADotnetMajor 10)) {
    Write-MaaWoADim '已安装，跳过'
}
else {
    Write-MaaWoAWarn '.NET 10 运行时缺失，MFAAvalonia 需要它'
    if (-not (Invoke-MaaWoAStep '.NET 运行时安装' { Install-MaaWoADotnet })) { exit 1 }
}
Write-MaaWoAOk '.NET 运行时就绪'

# 7. 部署 GUI --------------------------------------------------------------
Write-MaaWoAStep '部署 GUI 启动器'
if ((-not $Force) -and (Test-MaaWoALauncher)) {
    Write-MaaWoADim '已部署，刷新权限'
    Reset-MaaWoALauncherPermissions
}
elseif (-not (Invoke-MaaWoAStep '启动器部署' { Install-MaaWoALauncher })) {
    exit 1
}
Write-MaaWoAOk '启动器就绪'

# 8. 校验 ------------------------------------------------------------------
Write-MaaWoAStep '依赖校验'
if (Write-MaaWoAStatus) {
    Write-Host ''
    Write-MaaWoAOk '全部依赖已就绪'
    Write-MaaWoADim '启动应用：./run.ps1'
    exit 0
}

Write-Host ''
Write-MaaWoAError '仍有依赖缺失，请检查上方输出'
exit 1
