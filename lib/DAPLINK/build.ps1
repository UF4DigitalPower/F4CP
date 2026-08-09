param(
    [ValidateSet('all', 'if', 'bl')]
    [string]$Target = 'all'
)

$ErrorActionPreference = 'Stop'
$root = Split-Path -Parent $MyInvocation.MyCommand.Path
Set-Location $root

function Invoke-DaplinkBuild {
    param(
        [Parameter(Mandatory = $true)]
        [string]$Project
    )

    python tools\progen_compile.py -t make_gcc_arm --clean $Project
    Push-Location (Join-Path $root "projectfiles\make_gcc_arm\$Project")
    python ..\..\..\tools\post_build_script_gcc.py
    Pop-Location

    python tools\export_build_artifacts.py --target-project $Project --out-dir build
}

switch ($Target) {
    'all' {
        Invoke-DaplinkBuild 'stm32f103xb_custom_f103rb_if'
        Invoke-DaplinkBuild 'stm32f103xb_custom_bl'
    }
    'if' {
        Invoke-DaplinkBuild 'stm32f103xb_custom_f103rb_if'
    }
    'bl' {
        Invoke-DaplinkBuild 'stm32f103xb_custom_bl'
    }
}

