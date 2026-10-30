#requires -Version 7.0
param(
    [Parameter(Mandatory)][ValidatePattern('^[a-z0-9_]+$')][string]$RunName,
    [Parameter(Mandatory)][string]$TaskFile,
    [string]$Distribution='Ubuntu-24.04'
)
$ErrorActionPreference='Stop'
$repository=[IO.Path]::GetFullPath((Join-Path $PSScriptRoot '../..'))
. (Join-Path $PSScriptRoot 'guard_common.ps1')
$taskPath=[IO.Path]::GetFullPath((Join-Path $repository $TaskFile))
if(-not $taskPath.StartsWith($repository+[IO.Path]::DirectorySeparatorChar,[StringComparison]::OrdinalIgnoreCase)) { throw 'Task file must be inside this repository' }
$taskText=[IO.File]::ReadAllText($taskPath)
$task=$taskText | ConvertFrom-Json
$minimum=[double]$task.minimum_free_gib
if($minimum -notin @(6,7,7.5,8,9,10)) { throw 'Task admission must be 6 (CLI), 7 (native), 7.5 (headless video), 8, or a stricter 9/10 GiB' }
$taskEncoded=[Convert]::ToBase64String([Text.Encoding]::UTF8.GetBytes($taskText))
$command='source /opt/ros/jazzy/setup.bash && source install/setup.bash && exec python3 scripts/demand_guard.py --task-base64 '+$taskEncoded+' --host-memory results/'+$RunName+'/host_memory.json'
$code=Invoke-GuardedWsl -Repository $repository -RunName $RunName -Minimum $minimum -Command $command -Distribution $Distribution
exit $code
