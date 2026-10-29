#requires -Version 7.0
param(
    [Parameter(Mandatory)][ValidatePattern('^[a-z0-9_]+$')][string]$RunName,
    [Parameter(Mandatory)][string]$TaskFile,
    [string]$Distribution='Ubuntu-24.04'
)
$ErrorActionPreference='Stop'
$repository=[IO.Path]::GetFullPath((Join-Path $PSScriptRoot '../..'))
$linuxRepository=(& wsl.exe -d $Distribution -- wslpath -a $repository).Trim()
if ($LASTEXITCODE -ne 0 -or -not $linuxRepository.StartsWith('/')) { throw 'Cannot resolve repository inside WSL' }
$taskPath=[IO.Path]::GetFullPath((Join-Path $repository $TaskFile))
if(-not $taskPath.StartsWith($repository+[IO.Path]::DirectorySeparatorChar,[StringComparison]::OrdinalIgnoreCase)) { throw 'Task file must be inside this repository' }
$taskText=[IO.File]::ReadAllText($taskPath)
$task=$taskText | ConvertFrom-Json
$minimum=[double]$task.minimum_free_gib
if($minimum -notin @(6,7,7.5,8,9,10)) { throw 'Task admission must be 6 (CLI), 7 (native), 7.5 (headless video), 8, or a stricter 9/10 GiB' }
$taskEncoded=[Convert]::ToBase64String([Text.Encoding]::UTF8.GetBytes($taskText))
$runRoot=Join-Path $repository ('results/'+$RunName)
if(Test-Path -LiteralPath $runRoot) { throw 'Output already exists; preserve previous evidence' }
New-Item -ItemType Directory -Path $runRoot | Out-Null
$memoryFile=Join-Path $runRoot 'host_memory.json'
$script:memoryHistory=@()
function Write-MemorySample {
    $free=(Get-CimInstance Win32_OperatingSystem).FreePhysicalMemory/1MB
    $sampleTime=[DateTimeOffset]::UtcNow.ToUnixTimeMilliseconds()/1000.0
    $script:memoryHistory+=@{unix_s=$sampleTime;free_gib=$free}
    $script:memoryHistory=@($script:memoryHistory | Where-Object { $_.unix_s -ge $sampleTime-15 })
    @{unix_s=$sampleTime;free_gib=$free;history=$script:memoryHistory} |
        ConvertTo-Json -Depth 4 -Compress | Set-Content -LiteralPath ($memoryFile+'.tmp') -Encoding utf8
    Move-Item -LiteralPath ($memoryFile+'.tmp') -Destination $memoryFile -Force
    return $free
}
$first=Write-MemorySample
@{first_free_gib=$first;second_free_gib=$null;minimum_gib=$minimum;reserve_gib=4;admitted=$false} |
    ConvertTo-Json | Set-Content -LiteralPath (Join-Path $runRoot 'admission.json')
if($first -lt $minimum) { throw "Admission requires $minimum GiB free; observed $first" }
Start-Sleep -Seconds 5
$second=Write-MemorySample
@{first_free_gib=$first;second_free_gib=$second;separation_s=5;minimum_gib=$minimum;reserve_gib=4;admitted=($second -ge $minimum)} |
    ConvertTo-Json | Set-Content -LiteralPath (Join-Path $runRoot 'admission.json')
if($second -lt $minimum) { throw "Second admission sample below $minimum GiB" }
$command='source /opt/ros/jazzy/setup.bash && source install/setup.bash && exec python3 scripts/demand_guard.py --task-base64 '+$taskEncoded+' --host-memory results/'+$RunName+'/host_memory.json'
$info=[Diagnostics.ProcessStartInfo]::new()
$info.FileName='wsl.exe'
$info.UseShellExecute=$false
$info.CreateNoWindow=$true
$info.RedirectStandardOutput=$true
$info.RedirectStandardError=$true
foreach($arg in @('-d',$Distribution,'--cd',$linuxRepository,'--','bash','-lc',$command)) { $info.ArgumentList.Add($arg) }
$proc=[Diagnostics.Process]::Start($info)
$stdout=$proc.StandardOutput.ReadToEndAsync()
$stderr=$proc.StandardError.ReadToEndAsync()
$monitoringError=$null
try {
    while(-not $proc.WaitForExit(1000)) {
        $free=Write-MemorySample
        if($free -lt 5) { Set-Content -LiteralPath (Join-Path $runRoot 'STOP_REQUESTED') 'Preventive stop below 5 GiB' }
    }
} catch {
    $monitoringError=$_.ToString()
    Set-Content -LiteralPath (Join-Path $runRoot 'STOP_REQUESTED') $monitoringError
    if(-not $proc.WaitForExit(55000)) { throw 'Guard did not exit; inspect its recorded PID before scoped cleanup' }
} finally {
    if($proc.HasExited) {
        [IO.File]::WriteAllText((Join-Path $runRoot 'supervisor.stdout.log'),$stdout.GetAwaiter().GetResult())
        [IO.File]::WriteAllText((Join-Path $runRoot 'supervisor.stderr.log'),$stderr.GetAwaiter().GetResult())
        @{exit_code=$proc.ExitCode;monitoring_error=$monitoringError} | ConvertTo-Json | Set-Content -LiteralPath (Join-Path $runRoot 'supervisor.json')
    }
}
Write-Output "Demand task completed: exit=$($proc.ExitCode); evidence=$runRoot"
exit $proc.ExitCode
