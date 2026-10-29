#requires -Version 7.0
param(
    [Parameter(Mandatory)][ValidatePattern('^[a-z0-9_]+$')][string]$RunName,
    [ValidateSet('hybrid_gust','central_gust','hybrid_calm','hybrid_half_dt','hybrid_half_shape','capture')][string]$Case='hybrid_gust',
    [ValidateSet('overview','lower','upper')][string]$View='overview',
    [ValidateRange(1,342)][double]$Until=341,
    [switch]$AllViews,
    [switch]$NoGui,
    [switch]$FollowCarrier,
    [ValidateSet('buitrago_patio','buitrago_entre_pisos','ladera_agricola')][string]$Scenario,
    [ValidateSet('baseline','compact_candidate','revised_supports')][string]$Variant='revised_supports',
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
$minimum=if($Case -eq 'capture'){if($NoGui){10}else{14}}else{9}
function Write-MemorySample {
    $free=(Get-CimInstance Win32_OperatingSystem).FreePhysicalMemory/1MB
    @{unix_s=[DateTimeOffset]::UtcNow.ToUnixTimeMilliseconds()/1000.0; free_gib=$free} |
        ConvertTo-Json -Compress | Set-Content -LiteralPath ($memoryFile+'.tmp') -Encoding utf8
    Move-Item -LiteralPath ($memoryFile+'.tmp') -Destination $memoryFile -Force
    return $free
}
$first=Write-MemorySample
@{first_free_gib=$first;second_free_gib=$null;minimum_gib=$minimum;reserve_gib=4;admitted=$false} |
    ConvertTo-Json | Set-Content (Join-Path $runRoot 'admission.json')
if ($first -lt $minimum) { throw "Admission requires $minimum GiB free; observed $first" }
Start-Sleep -Seconds 5
$second=Write-MemorySample
@{first_free_gib=$first;second_free_gib=$second;separation_s=5;minimum_gib=$minimum;reserve_gib=4;admitted=($second -ge $minimum)} |
    ConvertTo-Json | Set-Content (Join-Path $runRoot 'admission.json')
if ($second -lt $minimum) { throw "Second admission sample below $minimum GiB" }
$command='source /opt/ros/jazzy/setup.bash && source install/setup.bash && exec python3 '
if ($Case -eq 'capture') {
    $command+='scripts/capture_loop.py --output results/'+$RunName+'/capture --host-memory results/'+$RunName+'/host_memory.json --video --timeout 1800 --view '+$View+' --until '+$Until.ToString([Globalization.CultureInfo]::InvariantCulture)
    if(-not $NoGui) { $command+=' --gui' }
    if($FollowCarrier) { $command+=' --follow-carrier 0' }
    if($AllViews) { $command+=' --all-views' }
} else {
    $command+='scripts/run_loop_guarded.py --output results/'+$RunName+'/'+$Case+' --host-memory results/'+$RunName+'/host_memory.json --case '+$Case
}
if($Scenario) { $command+=' --scenario '+$Scenario+' --variant '+$Variant }
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
    while(-not $proc.WaitForExit(2000)) {
        $free=Write-MemorySample
        if($free -lt 5) {
            Set-Content (Join-Path $runRoot 'STOP_REQUESTED') 'Preventive stop below 5 GiB to preserve 4 GiB reserve'
        }
    }
} catch {
    $failed=$_.ToString()
    Set-Content (Join-Path $runRoot 'STOP_REQUESTED') $failed
    if(-not $proc.WaitForExit(45000)) { throw 'Guard did not exit; inspect recorded PID before stopping' }
} finally {
    if($proc.HasExited) {
        [IO.File]::WriteAllText((Join-Path $runRoot 'supervisor.stdout.log'),$stdout.GetAwaiter().GetResult())
        [IO.File]::WriteAllText((Join-Path $runRoot 'supervisor.stderr.log'),$stderr.GetAwaiter().GetResult())
        @{exit_code=$proc.ExitCode;monitoring_error=$failed} | ConvertTo-Json | Set-Content (Join-Path $runRoot 'supervisor.json')
    }
}
Write-Output "Guard completed: exit=$($proc.ExitCode); evidence=$runRoot"
exit $proc.ExitCode
