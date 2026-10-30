#requires -Version 7.0
param(
    [Parameter(Mandatory)][ValidatePattern('^[a-z0-9_]+$')][string]$RunName,
    [Parameter(Mandatory)][ValidateSet('native','ros')][string]$Mode,
    [ValidateRange(0,101)][int]$RosDomainId=74,
    [string]$Distribution='Ubuntu-24.04'
)
$ErrorActionPreference='Stop'
$repository=[IO.Path]::GetFullPath((Join-Path $PSScriptRoot '../..'))
. (Join-Path $PSScriptRoot 'guard_common.ps1')
$minimum=9
$testFile=if($Mode -eq 'native'){'tests/test_ballasted_native.py'}else{'tests/test_ros_smoke.py'}
$command='source /opt/ros/jazzy/setup.bash && source install/setup.bash && exec python3 '+$testFile+
    ' --output results/'+$RunName+'/validation --host-memory results/'+$RunName+'/host_memory.json --timeout 120'
if($Mode -eq 'ros') { $command+=' --ros-domain-id '+$RosDomainId }
$code=Invoke-GuardedWsl -Repository $repository -RunName $RunName -Minimum $minimum -Command $command -Distribution $Distribution -Metadata @{mode=$Mode}
exit $code
