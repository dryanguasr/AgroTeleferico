#requires -Version 7.0
param(
    [Parameter(Mandatory)][ValidatePattern('^[a-z0-9_]+$')][string]$RunName,
    [Parameter(Mandatory)][ValidateSet('native','ros')][string]$Mode,
    [ValidateRange(0,101)][int]$RosDomainId=74,
    [string]$Distribution='Ubuntu-24.04'
)
$ErrorActionPreference='Stop'
$repository=[IO.Path]::GetFullPath((Join-Path $PSScriptRoot '../..'))
$linuxRepository=(& wsl.exe -d $Distribution -- wslpath -a $repository).Trim()
if ($LASTEXITCODE -ne 0 -or -not $linuxRepository.StartsWith('/')) { throw 'Cannot resolve repository inside WSL' }
$runRoot=Join-Path $repository ('results/'+$RunName)
if (Test-Path -LiteralPath $runRoot) { throw 'Output already exists; preserve previous evidence' }
New-Item -ItemType Directory -Path $runRoot | Out-Null
$memoryFile=Join-Path $runRoot 'host_memory.json'
function Write-MemorySample {
    $free=(Get-CimInstance Win32_OperatingSystem).FreePhysicalMemory/1MB
    @{unix_s=[DateTimeOffset]::UtcNow.ToUnixTimeMilliseconds()/1000.0; free_gib=$free} |
        ConvertTo-Json -Compress | Set-Content -LiteralPath ($memoryFile+'.tmp') -Encoding utf8
    Move-Item -LiteralPath ($memoryFile+'.tmp') -Destination $memoryFile -Force
    return $free
}
$first=Write-MemorySample
@{first_free_gib=$first;second_free_gib=$null;minimum_gib=9;reserve_gib=4;admitted=$false} |
    ConvertTo-Json | Set-Content -LiteralPath (Join-Path $runRoot 'admission.json')
if ($first -lt 9) { throw "Admission requires 9 GiB free; observed $first" }
Start-Sleep -Seconds 5
$second=Write-MemorySample
@{first_free_gib=$first;second_free_gib=$second;separation_s=5;minimum_gib=9;reserve_gib=4;admitted=($second -ge 9)} |
    ConvertTo-Json | Set-Content -LiteralPath (Join-Path $runRoot 'admission.json')
if ($second -lt 9) { throw 'Second admission sample below 9 GiB' }
$testFile=if($Mode -eq 'native'){'tests/test_ballasted_native.py'}else{'tests/test_ros_smoke.py'}
$command='source /opt/ros/jazzy/setup.bash && source install/setup.bash && exec python3 '+$testFile+
    ' --output results/'+$RunName+'/validation --host-memory results/'+$RunName+'/host_memory.json --timeout 120'
if($Mode -eq 'ros') { $command+=' --ros-domain-id '+$RosDomainId }
$info=[System.Diagnostics.ProcessStartInfo]::new()
$info.FileName='wsl.exe'
$info.UseShellExecute=$false
$info.CreateNoWindow=$true
$info.RedirectStandardOutput=$true
$info.RedirectStandardError=$true
foreach($arg in @('-d',$Distribution,'--cd',$linuxRepository,'--','bash','-lc',$command)) { $info.ArgumentList.Add($arg) }
$proc=[System.Diagnostics.Process]::Start($info)
$stdout=$proc.StandardOutput.ReadToEndAsync()
$stderr=$proc.StandardError.ReadToEndAsync()
$failed=$null
try {
    while(-not $proc.WaitForExit(1000)) {
        $free=Write-MemorySample
        if($free -lt 5) {
            Set-Content -LiteralPath (Join-Path $runRoot 'STOP_REQUESTED') 'Preventive stop below 5 GiB to preserve 4 GiB reserve'
        }
    }
} catch {
    $failed=$_.ToString()
    Set-Content -LiteralPath (Join-Path $runRoot 'STOP_REQUESTED') $failed
    if(-not $proc.WaitForExit(45000)) { throw 'Validation did not exit; inspect recorded PID before stopping' }
} finally {
    if($proc.HasExited) {
        [IO.File]::WriteAllText((Join-Path $runRoot 'supervisor.stdout.log'),$stdout.GetAwaiter().GetResult())
        [IO.File]::WriteAllText((Join-Path $runRoot 'supervisor.stderr.log'),$stderr.GetAwaiter().GetResult())
        @{mode=$Mode;exit_code=$proc.ExitCode;monitoring_error=$failed} |
            ConvertTo-Json | Set-Content -LiteralPath (Join-Path $runRoot 'supervisor.json')
    }
}
Write-Output "Validation completed: mode=$Mode exit=$($proc.ExitCode); evidence=$runRoot"
exit $proc.ExitCode
